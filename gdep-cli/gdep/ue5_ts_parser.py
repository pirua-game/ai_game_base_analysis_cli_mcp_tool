"""
gdep.ue5_ts_parser
UE5 C++ source parser based on Tree-sitter.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter_cpp
from tree_sitter import Language, Node, Parser

from .ue5_parser import (
    _IGNORE_DIRS,
    UE5_ENGINE_BASES,
    UE5_LIFECYCLE,
    UE5Class,
    UE5Function,
    UE5Project,
    UE5Property,
)

CPP_LANGUAGE = Language(tree_sitter_cpp.language())

# ── UE5 nested template types that cause tree-sitter infinite loops ──
# Must be applied BEFORE tree-sitter parsing (pre-processing in _clean_macros).
# Matches: TSoftClassPtr<UGameplayEffect>, TArray<TSubclassOf<UAbility>>, etc.
# Strategy: replace the entire "TypeName<...>" token with a plain identifier
#           so tree-sitter never sees the angle-bracket nesting.
RE_UE_TEMPLATE_TYPES = re.compile(
    r'\b(TSoftClassPtr|TSoftObjectPtr|TSubclassOf|TWeakObjectPtr|'
    r'TObjectPtr|TSharedPtr|TSharedRef|TWeakPtr|TArray|TMap|TSet|'
    r'TOptional)\s*<[^<>\n]*(?:<[^<>\n]*>[^<>\n]*)?>'
)

# Simple keyword regex — no parentheses involved (safe from backtracking)
RE_UE_SIMPLE = re.compile(
    r'\b(?:[A-Z][A-Z0-9_]*_API|FORCEINLINE|GENERATED_BODY|'
    r'GENERATED_UCLASS_BODY|GENERATED_USTRUCT_BODY)\b'
)

# Names of UE macros that are followed by an optional parenthesised argument list.
# These are stripped by the O(n) character scanner below — NOT by regex —
# so deeply-nested strings like Meta=(DisplayName="...") never cause backtracking.
_UE_MACRO_NAMES: frozenset[str] = frozenset({
    "UCLASS", "USTRUCT", "UENUM",
    "UPROPERTY", "UFUNCTION",
    "UE_DEPRECATED",
})

# ── Dependency Analysis Blacklist (Basic types and template shells) ──
BLACKLIST_TYPES = {
    "int", "int32", "uint32", "int64", "uint64", "float", "double", "bool", "void",
    "uint8", "int8", "uint16", "int16", "long", "short", "char", "size_t",
    "TObjectPtr", "TSubclassOf", "TArray", "TMap", "TSet", "TWeakObjectPtr", "TSharedPtr", "TSharedRef",
    "FVector", "FRotator", "FQuat", "FTransform", "FString", "FName", "FText",
    "FColor", "FLinearColor", "FIntPoint", "FGuid", "FDateTime", "FTimespan",
    "FVector2D", "FTimerHandle", "UClass", "UStruct", "UObject", "AActor", "Super",
    # _clean_macros placeholder — must never appear as a real dependency
    "UE5TemplateType", "UE5TemplateArg",
}

def _normalize_cpp_type(t: str) -> str:
    """Normalize C++ type and extract core class name (recursive)"""
    if not t: return ""
    t = t.strip()

    # 1. Remove comments
    t = re.sub(r'//.*', '', t)
    t = re.sub(r'/\*.*?\*/', '', t, flags=re.DOTALL)

    # 2. Remove prefixes and qualifiers (const, class, struct, enum, unsigned, etc.)
    t = re.sub(r'\b(const|class|struct|enum|unsigned|signed|static|volatile|virtual)\b', '', t).strip()

    # 3. Handle templates (TObjectPtr<AActor*> -> AActor)
    # Extract arguments of the outermost template
    m = re.search(r'<([^>]+)>', t)
    if m:
        container_name = t.split('<')[0].strip()
        inner = m.group(1).split(',')[0].strip()

        # If it's a blacklisted template shell (TObjectPtr, TArray, etc.), return the inner type
        if container_name in BLACKLIST_TYPES:
            return _normalize_cpp_type(inner)

        # For other templates, the inner type is usually the core dependency.
        return _normalize_cpp_type(inner)

    # 4. Remove pointers, references, and array symbols
    t = t.replace('*', '').replace('&', '').strip()
    t = re.sub(r'\[.*?\]', '', t).strip()

    # 5. Remove namespaces (A::B::C -> C)
    t = t.split('::')[-1].strip()

    # 6. Invalidate if composed only of numeric literals or special characters
    if not t or not t[0].isalpha() and t[0] != '_':
        return ""

    return t

class UE5TSParser:
    def __init__(self):
        self.parser = Parser(CPP_LANGUAGE)

    def _clean_macros(self, content: str) -> str:
        """Blank out AST-breaking UE5 macros before feeding content to tree-sitter.

        Two-pass strategy — both passes are O(n) with no regex backtracking:

        Pass 1 – RE_UE_TEMPLATE_TYPES  (compiled regex, safe: [^<>\\n]* has no ambiguity)
            TSoftClassPtr<UGameplayEffect>  →  UE5TemplateType<spaces>

        Pass 2 – RE_UE_SIMPLE  (simple keyword regex, no paren matching needed)
            FORCEINLINE / *_API / GENERATED_BODY* → spaces

        Pass 3 – O(n) character scanner for paren-bearing macros
            UCLASS(BlueprintType, Meta=(DisplayName="..."))  →  spaces
            UPROPERTY(...) / UFUNCTION(...) / USTRUCT(...) / UENUM(...) / UE_DEPRECATED(...)
            The scanner never backtracks: it counts '(' depth and copies nothing.
        """
        # ── Pass 1: nested template types ──────────────────────────────────────
        # Also build orig_map: {byte_start -> original_type_str} so that
        # _parse_member can recover the real type name for describe output.
        orig_map: dict[int, str] = {}

        def _replace_template(m: re.Match) -> str:
            ph = "UE5TemplateType"
            original = m.group(0)
            span = len(original)
            # Record original type at the match start position
            orig_map[m.start()] = original
            if span >= len(ph):
                return ph + " " * (span - len(ph))
            # Span is shorter than placeholder: blank it out entirely
            return " " * span

        content = RE_UE_TEMPLATE_TYPES.sub(_replace_template, content)
        self._orig_map = orig_map  # expose for _parse_member

        # ── Pass 2: simple keyword macros (no parens) ──────────────────────────
        content = RE_UE_SIMPLE.sub(lambda m: " " * len(m.group(0)), content)

        # ── Pass 3: O(n) character scanner for paren-bearing macros ────────────
        # Scans left-to-right; when a known macro name is found, consumes the
        # optional whitespace + parenthesised argument list and blanks them out.
        # Handles arbitrary nesting depth and quoted strings — no backtracking.
        result = list(content)          # mutable char array
        n = len(content)
        i = 0
        while i < n:
            # Fast-forward: UE macro names all start with U or u
            ch = content[i]
            if ch not in ('U', 'u'):
                i += 1
                continue

            # Check whether a known macro name starts here
            matched_name: str | None = None
            for name in _UE_MACRO_NAMES:
                end = i + len(name)
                if content[i:end] == name:
                    # Must be followed by non-identifier char (word boundary)
                    if end >= n or not (content[end].isalnum() or content[end] == '_'):
                        matched_name = name
                        break

            if matched_name is None:
                i += 1
                continue

            # Blank out the macro keyword itself
            end_name = i + len(matched_name)
            for k in range(i, end_name):
                result[k] = ' '
            i = end_name

            # Skip optional whitespace
            while i < n and content[i] in (' ', '\t', '\r', '\n'):
                i += 1

            # If followed by '(', consume the entire balanced paren group
            if i < n and content[i] == '(':
                depth = 0
                in_str = False
                str_ch = ''
                while i < n:
                    c = content[i]
                    if in_str:
                        if c == '\\':
                            result[i] = ' '
                            i += 1
                            if i < n:
                                result[i] = ' '
                                i += 1
                            continue
                        if c == str_ch:
                            in_str = False
                        result[i] = ' '
                        i += 1
                    else:
                        if c in ('"', "'"):
                            in_str = True
                            str_ch = c
                            result[i] = ' '
                            i += 1
                        elif c == '(':
                            depth += 1
                            result[i] = ' '
                            i += 1
                        elif c == ')':
                            depth -= 1
                            result[i] = ' '
                            i += 1
                            if depth == 0:
                                break
                        else:
                            result[i] = ' '
                            i += 1

        return ''.join(result)

    def parse_file(self, file_path: Path, deep: bool = False) -> list[UE5Class]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        self._deep = deep
        self._orig_map: dict[int, str] = {}   # populated by _clean_macros
        clean_content = self._clean_macros(content)

        # ── tree-sitter parse ─────────────────────────────────────
        # Nested template types (TSoftClassPtr<X>, TArray<TSubclassOf<Y>>, etc.)
        # are pre-sanitised by _clean_macros() → RE_UE_TEMPLATE_TYPES above,
        # so tree-sitter should never see angle-bracket nesting that triggers hang.
        # The old ThreadPoolExecutor timeout trick is removed: Python GIL means
        # the thread never actually interrupts a hung C extension anyway.
        try:
            tree = self.parser.parse(bytes(clean_content, "utf8"))
        except Exception:
            return []

        root = tree.root_node

        self._classes = []
        self._file_path = file_path
        self._walk(root)
        return self._classes

    def _fallback_regex_parse(self, file_path: Path,
                              content: str) -> list[UE5Class]:
        """Lightweight regex-based fallback when tree-sitter hangs."""
        from .ue5_parser import _parse_file as _regex_parse_file
        try:
            return _regex_parse_file(file_path)
        except Exception:
            return []

    def _walk(self, node: Node):
        if node.type in ("class_specifier", "struct_specifier"):
            self._handle_class_specifier(node)
        elif node.type == "enum_specifier":
            self._handle_enum_specifier(node)
        elif node.type == "namespace_definition":
            self._handle_namespace(node)
            return  # children handled inside _handle_namespace
        elif node.type == "function_definition" and self._deep:
            # Analyze method body (including out-of-class definitions)
            self._handle_out_of_class_function(node)

        for child in node.children:
            self._walk(child)

    def _handle_namespace(self, node: Node):
        """Parse namespace_definition as a pseudo-class so tools like
        explore_class_semantics can find utility namespaces."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        ns_name = name_node.text.decode("utf-8").strip()
        if not ns_name or not ns_name[0].isupper():
            return  # skip anonymous or lowercase namespaces (e.g. detail::)

        cls = UE5Class(name=ns_name, kind="namespace", source_file=str(self._file_path))

        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type in ("function_definition", "declaration"):
                    self._parse_namespace_func(child, cls)
                elif child.type in ("class_specifier", "struct_specifier"):
                    self._handle_class_specifier(child)
                elif child.type == "enum_specifier":
                    self._handle_enum_specifier(child)

        self._classes.append(cls)

    def _parse_namespace_func(self, node: Node, cls: UE5Class):
        """Extract a free function inside a namespace as a UE5Function."""
        decl = node.child_by_field_name("declarator")
        if not decl:
            return

        # Walk down to find function_declarator
        curr = decl
        while curr and curr.type != "function_declarator":
            curr = curr.named_child(0) if curr.named_child_count > 0 else None
        if not curr:
            return

        name_node = curr.child_by_field_name("declarator")
        if not name_node:
            return

        func_name = name_node.text.decode("utf-8").strip()
        if not func_name or func_name.startswith("~"):
            return

        ret_type = ""
        type_node = node.child_by_field_name("type")
        if type_node:
            ret_type = _normalize_cpp_type(type_node.text.decode("utf-8"))

        fn = UE5Function(name=func_name, return_type=ret_type, access="public")

        params_node = curr.child_by_field_name("parameters")
        if params_node:
            for param in params_node.children:
                if param.type == "parameter_declaration":
                    p_type = param.child_by_field_name("type")
                    if p_type:
                        fn.params.append(_normalize_cpp_type(p_type.text.decode("utf-8")))

        cls.functions.append(fn)

    def _handle_enum_specifier(self, node: Node):
        """Parse UENUM"""
        name_node = node.child_by_field_name("name")
        if not name_node: return

        enum_name = name_node.text.decode("utf-8").strip()
        # Normalize name (remove prefixes, etc.)
        norm_name = _normalize_cpp_type(enum_name)
        cls = UE5Class(name=norm_name, kind="enum", source_file=str(self._file_path))

        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "enumerator":
                    enum_val = child.child_by_field_name("name")
                    if enum_val:
                        cls.enum_values.append(enum_val.text.decode("utf-8").strip())

        self._classes.append(cls)

    def _handle_class_specifier(self, node: Node):
        cls_name = None
        for child in node.children:
            if child.type == "type_identifier":
                cls_name = child.text.decode("utf-8").strip()
                break

        if cls_name:
            # Ignore forward declarations without bodies (e.g., class FName;)
            has_body = any(c.type in ("field_declaration_list", "compound_statement") for c in node.children)
            if not has_body:
                return

            if cls_name in UE5_ENGINE_BASES:
                return

            # Normalize name (remove prefixes, etc.)
            norm_name = _normalize_cpp_type(cls_name)

            cls = UE5Class(
                name=norm_name,
                kind="class" if node.type == "class_specifier" else "struct",
                source_file=str(self._file_path)
            )

            self._current_access = "private"
            self._pending_macro = None

            # Iterate through children
            for child in node.children:
                if child.type == "base_class_clause":
                    self._extract_bases_from_clause(child, cls)
                elif child.type in ("field_declaration_list", "compound_statement"):
                    self._parse_body_block(child, cls)

            self._classes.append(cls)

    def _handle_out_of_class_function(self, node: Node):
        """Analyze out-of-class defined methods (usually in .cpp)"""
        decl = node.child_by_field_name("declarator")
        if not decl: return

        # Check for AMyClass::BeginPlay() format
        target_cls = None
        func_name = None
        curr = decl
        while curr and curr.type not in ("qualified_identifier", "identifier"):
            curr = curr.child_by_field_name("declarator")

        if curr and curr.type == "qualified_identifier":
            scope = curr.child_by_field_name("scope")
            name_node = curr.child_by_field_name("name")
            if scope and name_node:
                target_cls = scope.text.decode("utf-8").strip()
                func_name = name_node.text.decode("utf-8").strip()

        if target_cls:
            norm_name = _normalize_cpp_type(target_cls)
            temp_cls = UE5Class(name=norm_name, kind="class_body_only", source_file=str(self._file_path))

            body = node.child_by_field_name("body")
            if body:
                self._analyze_body_dependencies(body, temp_cls)

                if func_name:
                    # Create function object to store body_text
                    func = UE5Function(name=func_name, source_file=str(self._file_path))
                    func.body_text = body.text.decode("utf-8")
                    if func_name in UE5_LIFECYCLE:
                        func.is_lifecycle = True
                    temp_cls.functions.append(func)

            self._classes.append(temp_cls)

    def _extract_bases_from_clause(self, clause_node: Node, cls: UE5Class):
        """Extract all parent classes from base_class_clause node (excluding template arguments)"""
        # base_class_clause -> [':', 'public', 'type_identifier', ',', 'template_type', ...]
        for child in clause_node.children:
            base_name = None
            if child.type == "type_identifier":
                base_name = child.text.decode("utf-8").strip()
            elif child.type == "qualified_identifier":
                # Namespace::BaseClass -> Use full text
                base_name = child.text.decode("utf-8").strip()
            elif child.type == "template_type":
                # TBase<Other> -> Use child_by_field_name('name') to extract only TBase
                name_node = child.child_by_field_name("name")
                if name_node:
                    base_name = name_node.text.decode("utf-8").strip()
                else:
                    # Fallback: the first child is usually the type name
                    base_name = child.named_child(0).text.decode("utf-8").strip()

            if base_name and base_name not in ("public", "protected", "private", "virtual"):
                if base_name != cls.name and base_name not in cls.bases:
                    cls.bases.append(base_name)

    def _parse_body_block(self, block_node: Node, cls: UE5Class):
        for child in block_node.children:
            if child.type not in ("{", "}"):
                self._parse_member(child, cls)

        # --deep analysis (method bodies defined inside class)
        if self._deep:
            for child in block_node.children:
                if child.type == "function_definition":
                    body = child.child_by_field_name("body")
                    if body:
                        self._analyze_body_dependencies(body, cls)

    def _analyze_body_dependencies(self, body_node: Node, cls: UE5Class):
        """Deep analysis of dependencies within method bodies"""
        def collect(n: Node):
            # 1. Template-based calls and types (NewObject<T>, Cast<T>, GetSubsystem<T>, etc.)
            if n.type in ("template_type", "template_method", "template_function"):
                # Extract template arguments
                args = n.child_by_field_name("arguments")
                if args:
                    for arg in args.children:
                        # Extract type_descriptor or direct type_identifier
                        if arg.type in ("type_descriptor", "type_identifier"):
                            self._add_dep(arg.text.decode("utf-8"), cls)
                        elif arg.named_child_count > 0:
                            # Recursive text extraction for complex types like A*
                            self._add_dep(arg.text.decode("utf-8"), cls)

            # 2. Static access and reflection (Namespace::Class, Class::StaticClass)
            if n.type == "qualified_identifier":
                full_text = n.text.decode("utf-8").strip()
                if "::" in full_text:
                    parts = full_text.split("::")
                    # Handle StaticClass(), GetClass() patterns: extract Class if Class::StaticClass
                    if parts[-1] in ("StaticClass", "GetClass", "GetStaticClass"):
                        if len(parts) >= 2:
                            self._add_dep(parts[-2], cls)
                    else:
                        # General static member/function access: add all scopes except last element
                        for p in parts[:-1]:
                            self._add_dep(p, cls)

            # 3. Object instantiation (new Class)
            if n.type == "new_expression":
                type_node = n.child_by_field_name("type")
                if type_node:
                    self._add_dep(type_node.text.decode("utf-8"), cls)

            # 4. Local variable declaration
            if n.type == "declaration":
                type_node = n.child_by_field_name("type")
                if type_node:
                    self._add_dep(type_node.text.decode("utf-8"), cls)

            for child in n.children:
                collect(child)

        collect(body_node)

    def _add_dep(self, type_str: str, cls: UE5Class):
        # Use dedicated normalization logic and blacklist
        t = _normalize_cpp_type(type_str)

        if t and t not in BLACKLIST_TYPES and t != cls.name:
            if t not in cls.dependencies:
                cls.dependencies.append(t)

    def _parse_member(self, node: Node, cls: UE5Class):
        # 1. Access specifiers
        if node.type == "access_specifier":
            self._current_access = node.text.decode("utf-8").replace(":", "").strip()
            return

        # 2. Labeled statement (public:)
        if node.type == "labeled_statement":
            label = node.child_by_field_name("label")
            if label:
                self._current_access = label.text.decode("utf-8").replace(":", "").strip()
            for child in node.children:
                if child.type not in ("label", ":"):
                    self._parse_member(child, cls)
            return

        # 3. Macro detection
        if node.type == "expression_statement" and node.named_child_count > 0:
            call = node.named_child(0)
            if call and call.type == "call_expression":
                func = call.child_by_field_name("function")
                if func and func.text:
                    m_name = func.text.decode("utf-8")
                    if m_name in ("UPROPERTY", "UFUNCTION"):
                        self._pending_macro = (m_name, self._get_args(call))
                        return

        # 4. Variable/field declaration
        if node.type in ("field_declaration", "declaration"):
            # Check for function declaration first
            f_decl = self._find_function_declarator(node)
            if f_decl:
                self._extract_function(node, f_decl, cls)
                self._pending_macro = None
                return

            type_node = node.child_by_field_name("type")
            if type_node:
                t_str = type_node.text.decode("utf-8").strip()
                # _clean_macros replaced UE5 template types with "UE5TemplateType".
                # Recover the original type string from _orig_map using the node's
                # byte offset, so describe output shows e.g. "TSoftClassPtr<UGameplayEffect>"
                # instead of the placeholder.
                if "UE5TemplateType" in t_str:
                    byte_start = type_node.start_byte
                    # UPROPERTY macro removal (Pass 3) shifts byte offsets by
                    # up to ~80 bytes per macro. Scan a generous window around
                    # the node's start byte to find the matching orig_map entry.
                    recovered = None
                    for delta in range(-80, 16):
                        recovered = self._orig_map.get(byte_start + delta)
                        if recovered:
                            break
                    if recovered:
                        t_str = recovered.strip()
                    else:
                        t_str = t_str.replace("UE5TemplateType", "").strip(" *&").strip() or "?"
                # Find declarator
                for child in node.children:
                    n_str = None
                    if child.type in ("field_identifier", "identifier"):
                        n_str = child.text.decode("utf-8").strip()
                    elif child.type == "pointer_declarator":
                        inner = child.child_by_field_name("declarator")
                        if inner:
                            n_str = inner.text.decode("utf-8").strip()
                            # Maintain pointer type
                            t_str += "*"

                    if n_str:
                        cls.properties.append(UE5Property(name=n_str, type_=t_str, access=self._current_access))
                        break
            self._pending_macro = None

        # 5. Function definition
        if node.type == "function_definition":
            f_decl = self._find_function_declarator(node)
            if f_decl:
                self._extract_function(node, f_decl, cls)
            self._pending_macro = None

    def _find_function_declarator(self, node: Node) -> Node | None:
        if node.type == "function_declarator":
            return node
        for child in node.children:
            res = self._find_function_declarator(child)
            if res: return res
        return None

    def _extract_function(self, node: Node, f_decl: Node, cls: UE5Class):
        name_node = f_decl.child_by_field_name("declarator")
        if name_node:
            f_name = name_node.text.decode("utf-8").strip()
            if f_name in ("GENERATED_BODY", "UPROPERTY", "UFUNCTION", "UCLASS", "USTRUCT"):
                return
            ret_node = node.child_by_field_name("type")
            rt_str = ret_node.text.decode("utf-8").strip() if ret_node else "void"

            func = UE5Function(name=f_name, return_type=rt_str, access=self._current_access)
            func.source_file = cls.source_file
            if f_name in UE5_LIFECYCLE:
                func.is_lifecycle = True

            full_text = node.text.decode("utf-8")
            if "virtual" in full_text: func.is_virtual = True
            if "override" in full_text: func.is_override = True

            # Extract body text for linter
            if node.type == "function_definition":
                body = node.child_by_field_name("body")
                if body:
                    func.body_text = body.text.decode("utf-8")

            cls.functions.append(func)

    def _get_args(self, call_node: Node) -> str:
        args_node = call_node.child_by_field_name("arguments")
        if args_node:
            text = args_node.text.decode("utf-8")
            return text[1:-1].strip()
        return ""

def parse_project(root_path: str, deep: bool = False) -> UE5Project:
    parser = UE5TSParser()
    project = UE5Project(root=Path(root_path))

    # 1. Header file parsing (basic structure)
    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for file in files:
            if file.endswith((".h", ".hpp")):
                path = Path(root) / file
                classes = parser.parse_file(path, deep=deep)
                for cls in classes:
                    if cls.kind == "enum":
                        project.enums[cls.name] = cls
                    elif cls.kind == "struct":
                        project.structs[cls.name] = cls
                    else:
                        project.classes[cls.name] = cls

    # 2. If deep mode, analyze .cpp files and merge dependencies
    if deep:
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
            for file in files:
                if file.endswith(".cpp"):
                    path = Path(root) / file
                    temp_classes = parser.parse_file(path, deep=True)
                    for tc in temp_classes:
                        if tc.kind == "class_body_only":
                            if tc.name in project.classes:
                                target = project.classes[tc.name]
                                # Merge dependencies
                                for dep in tc.dependencies:
                                    if dep not in target.dependencies:
                                        target.dependencies.append(dep)
                                # Merge functions (update body_text if found)
                                for tf in tc.functions:
                                    found = False
                                    for f in target.functions:
                                        if f.name == tf.name:
                                            f.body_text = tf.body_text
                                            f.source_file = tf.source_file
                                            found = True
                                            break
                                    if not found:
                                        target.functions.append(tf)

    return project

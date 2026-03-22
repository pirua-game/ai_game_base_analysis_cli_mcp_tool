"""
gdep.cpp_ts_parser
Standard C++ source parser based on Tree-sitter.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter_cpp
from tree_sitter import Language, Node, Parser

from .cpp_parser import (
    _IGNORE_DIRS,
    CPP_BASIC_TYPES,
    CPPClass,
    CPPFunction,
    CPPProject,
    CPPProperty,
)

CPP_LANGUAGE = Language(tree_sitter_cpp.language())

def _normalize_cpp_type(t: str) -> str:
    """Normalize C++ type and extract core class name (recursive)"""
    if not t: return ""
    t = t.strip()

    # 1. Remove comments
    t = re.sub(r'//.*', '', t)
    t = re.sub(r'/\*.*?\*/', '', t, flags=re.DOTALL)

    # 2. Remove prefixes and qualifiers (const, class, struct, enum, unsigned, etc.)
    t = re.sub(r'\b(const|class|struct|enum|unsigned|signed|static|volatile|virtual)\b', '', t).strip()

    # 3. Handle templates (std::vector<MyClass*> -> MyClass)
    m = re.search(r'<([^>]+)>', t)
    if m:
        container_name = t.split('<')[0].strip()
        inner = m.group(1).split(',')[0].strip()

        # If it's a basic container, return the inner type
        if container_name in CPP_BASIC_TYPES or "std::" in container_name:
            return _normalize_cpp_type(inner)

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

class CPPTSParser:
    def __init__(self):
        self.parser = Parser(CPP_LANGUAGE)

    def parse_file(self, file_path: Path, deep: bool = False) -> list[CPPClass]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        self._deep = deep
        # Minimal macro cleaning for standard C++
        tree = self.parser.parse(bytes(content, "utf8"))
        root = tree.root_node

        self._classes = []
        self._file_path = file_path
        self._walk(root)
        return self._classes

    def _walk(self, node: Node):
        if node.type in ("class_specifier", "struct_specifier"):
            self._handle_class_specifier(node)
        elif node.type == "enum_specifier":
            self._handle_enum_specifier(node)
        elif node.type == "function_definition" and self._deep:
            self._handle_out_of_class_function(node)

        for child in node.children:
            self._walk(child)

    def _handle_enum_specifier(self, node: Node):
        name_node = node.child_by_field_name("name")
        if not name_node: return

        enum_name = name_node.text.decode("utf-8").strip()
        norm_name = _normalize_cpp_type(enum_name)
        cls = CPPClass(name=norm_name, kind="enum", source_file=str(self._file_path))

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
            has_body = any(c.type in ("field_declaration_list", "compound_statement") for c in node.children)
            if not has_body:
                return

            norm_name = _normalize_cpp_type(cls_name)
            cls = CPPClass(
                name=norm_name,
                kind="class" if node.type == "class_specifier" else "struct",
                source_file=str(self._file_path)
            )

            self._current_access = "private"

            for child in node.children:
                if child.type == "base_class_clause":
                    self._extract_bases_from_clause(child, cls)
                elif child.type in ("field_declaration_list", "compound_statement"):
                    self._parse_body_block(child, cls)

            self._classes.append(cls)

    def _handle_out_of_class_function(self, node: Node):
        decl = node.child_by_field_name("declarator")
        if not decl: return

        target_cls = None
        curr = decl
        while curr and curr.type not in ("qualified_identifier", "identifier"):
            curr = curr.child_by_field_name("declarator")

        if curr and curr.type == "qualified_identifier":
            scope = curr.child_by_field_name("scope")
            if scope:
                target_cls = scope.text.decode("utf-8").strip()

        if target_cls:
            norm_name = _normalize_cpp_type(target_cls)
            temp_cls = CPPClass(name=norm_name, kind="class_body_only")
            body = node.child_by_field_name("body")
            if body:
                self._analyze_body_dependencies(body, temp_cls)
            self._classes.append(temp_cls)

    def _extract_bases_from_clause(self, clause_node: Node, cls: CPPClass):
        for child in clause_node.children:
            base_name = None
            if child.type == "type_identifier":
                base_name = child.text.decode("utf-8").strip()
            elif child.type == "qualified_identifier":
                base_name = child.text.decode("utf-8").strip()
            elif child.type == "template_type":
                name_node = child.child_by_field_name("name")
                if name_node:
                    base_name = name_node.text.decode("utf-8").strip()
                else:
                    base_name = child.named_child(0).text.decode("utf-8").strip()

            if base_name and base_name not in ("public", "protected", "private", "virtual"):
                if base_name != cls.name and base_name not in cls.bases:
                    cls.bases.append(base_name)

    def _parse_body_block(self, block_node: Node, cls: CPPClass):
        for child in block_node.children:
            if child.type not in ("{", "}"):
                self._parse_member(child, cls)

        if self._deep:
            for child in block_node.children:
                if child.type == "function_definition":
                    body = child.child_by_field_name("body")
                    if body:
                        self._analyze_body_dependencies(body, cls)

    def _analyze_body_dependencies(self, body_node: Node, cls: CPPClass):
        def collect(n: Node):
            if n.type in ("template_type", "template_method", "template_function"):
                args = n.child_by_field_name("arguments")
                if args:
                    for arg in args.children:
                        if arg.type in ("type_descriptor", "type_identifier"):
                            self._add_dep(arg.text.decode("utf-8"), cls)
                        elif arg.named_child_count > 0:
                            self._add_dep(arg.text.decode("utf-8"), cls)

            if n.type == "qualified_identifier":
                full_text = n.text.decode("utf-8").strip()
                if "::" in full_text:
                    parts = full_text.split("::")
                    for p in parts[:-1]:
                        self._add_dep(p, cls)

            if n.type == "new_expression":
                type_node = n.child_by_field_name("type")
                if type_node:
                    self._add_dep(type_node.text.decode("utf-8"), cls)

            if n.type == "declaration":
                type_node = n.child_by_field_name("type")
                if type_node:
                    self._add_dep(type_node.text.decode("utf-8"), cls)

            for child in n.children:
                collect(child)

        collect(body_node)

    def _add_dep(self, type_str: str, cls: CPPClass):
        t = _normalize_cpp_type(type_str)
        if t and t not in CPP_BASIC_TYPES and t != cls.name:
            if t not in cls.dependencies:
                cls.dependencies.append(t)

    def _parse_member(self, node: Node, cls: CPPClass):
        if node.type == "access_specifier":
            self._current_access = node.text.decode("utf-8").replace(":", "").strip()
            return

        if node.type == "labeled_statement":
            label = node.child_by_field_name("label")
            if label:
                self._current_access = label.text.decode("utf-8").replace(":", "").strip()
            for child in node.children:
                if child.type not in ("label", ":"):
                    self._parse_member(child, cls)
            return

        if node.type in ("field_declaration", "declaration"):
            f_decl = self._find_function_declarator(node)
            if f_decl:
                self._extract_function(node, f_decl, cls)
                return

            type_node = node.child_by_field_name("type")
            if type_node:
                t_str = type_node.text.decode("utf-8").strip()
                for child in node.children:
                    n_str = None
                    if child.type in ("field_identifier", "identifier"):
                        n_str = child.text.decode("utf-8").strip()
                    elif child.type == "pointer_declarator":
                        inner = child.child_by_field_name("declarator")
                        if inner:
                            n_str = inner.text.decode("utf-8").strip()
                            t_str += "*"

                    if n_str:
                        cls.properties.append(CPPProperty(name=n_str, type_=t_str, access=self._current_access))
                        break

        if node.type == "function_definition":
            f_decl = self._find_function_declarator(node)
            if f_decl:
                self._extract_function(node, f_decl, cls)

    def _find_function_declarator(self, node: Node) -> Node | None:
        if node.type == "function_declarator":
            return node
        for child in node.children:
            res = self._find_function_declarator(child)
            if res: return res
        return None

    def _extract_function(self, node: Node, f_decl: Node, cls: CPPClass):
        name_node = f_decl.child_by_field_name("declarator")
        if name_node:
            f_name = name_node.text.decode("utf-8").strip()
            ret_node = node.child_by_field_name("type")
            rt_str = ret_node.text.decode("utf-8").strip() if ret_node else "void"

            func = CPPFunction(name=f_name, return_type=rt_str, access=self._current_access)

            full_text = node.text.decode("utf-8")
            if "virtual" in full_text: func.is_virtual = True
            if "override" in full_text: func.is_override = True
            if "static" in full_text: func.is_static = True
            if "const" in full_text: func.is_const = True

            cls.functions.append(func)

def parse_project(root_path: str, deep: bool = False) -> CPPProject:
    parser = CPPTSParser()
    project = CPPProject(root=Path(root_path))

    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for file in files:
            if file.endswith((".h", ".hpp", ".hxx")):
                path = Path(root) / file
                classes = parser.parse_file(path, deep=deep)
                for cls in classes:
                    if cls.kind == "enum":
                        project.enums[cls.name] = cls
                    elif cls.kind == "struct":
                        project.structs[cls.name] = cls
                    else:
                        project.classes[cls.name] = cls

    if deep:
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
            for file in files:
                if file.endswith((".cpp", ".cc", ".cxx")):
                    path = Path(root) / file
                    temp_classes = parser.parse_file(path, deep=True)
                    for tc in temp_classes:
                        if tc.kind == "class_body_only":
                            if tc.name in project.classes:
                                target = project.classes[tc.name]
                                for dep in tc.dependencies:
                                    if dep not in target.dependencies:
                                        target.dependencies.append(dep)

    return project

"""
gdep.cpp_flow
Standard C++ method call flow analyzer.
Reuses the core extraction logic from ue5_flow, without UE5-specific
Blueprint bridge / GAS patterns.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# ── Identifiers to always ignore ──────────────────────────────
_IGNORE_CALLS = {
    "if", "for", "while", "switch", "return", "new", "delete",
    "sizeof", "decltype", "static_assert", "nullptr", "true", "false",
    "std", "cout", "cerr", "endl", "printf", "fprintf", "sprintf",
    "malloc", "calloc", "realloc", "free",
    "assert", "ASSERT", "LOG", "LOGE", "LOGD", "LOGW",
    "CC_SAFE_DELETE", "CC_SAFE_RELEASE", "CC_SAFE_RETAIN",
    "Schedule", "unschedule",  # Cocos2d-x scheduler (handled separately)
}

_IGNORE_CLASS_PREFIXES = (
    "std::", "boost::", "glm::",
    "cocos2d::",        # Cocos2d-x 내부 (디렉토리 외에 호출 수준도 차단)
    "nlohmann::",       # JSON 라이브러리
    "__",               # 컴파일러 내부 심볼
)

_DELEGATE_FUNC_NAMES = {
    "bind", "connect", "disconnect", "addEventListenerWithSceneGraphPriority",
    "addEventListenerWithFixedPriority", "addEventListener",
    "schedule", "scheduleOnce", "scheduleUpdate",
    "AddDynamic", "BindUObject", "BindDynamic",  # UE5 delegates
}

# ── Helpers (shared with ue5_flow logic) ──────────────────────

def _balanced_paren_end(text: str, start: int) -> int:
    assert text[start] == '('
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return i
    return len(text) - 1


def _remove_comments(text: str) -> str:
    result = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == '/' and i + 1 < n and text[i + 1] == '*':
            end = text.find('*/', i + 2)
            if end == -1:
                break
            i = end + 2
        elif text[i] == '/' and i + 1 < n and text[i + 1] == '/':
            while i < n and text[i] != '\n':
                i += 1
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


def _masked_body(body: str) -> str:
    """Mask delegate / callback registration calls so their arguments
    are not mistaken for direct function calls."""
    result = list(body)
    i, n = 0, len(body)
    while i < n:
        for fname in _DELEGATE_FUNC_NAMES:
            fl = len(fname)
            if body[i:i + fl] == fname:
                j = i + fl
                while j < n and body[j] in ' \t':
                    j += 1
                if j < n and body[j] == '(':
                    end = _balanced_paren_end(body, j)
                    for k in range(i, end + 1):
                        result[k] = ' '
                    i = end + 1
                    break
        else:
            i += 1
    return ''.join(result)


_FUNC_PTR_PAT = re.compile(r'&\s*\w+\s*::\s*\w+')

_COND_KEYWORD_PAT = re.compile(r'\b(if|switch|while|for)\s*\(')

# UE5 delegate binding: AddDynamic(this, &AMyClass::OnHit) → edge to AMyClass.OnHit
_DELEGATE_BIND_PAT = re.compile(
    r'(?:AddDynamic|BindUObject|BindDynamic)\s*\(\s*[^,]+,\s*&([A-Za-z0-9_]+)::([A-Za-z0-9_]+)\s*\)'
)


def _extract_condition_at(body: str, call_offset: int) -> str:
    """Return 'keyword: condition_text' for the innermost conditional wrapping call_offset."""
    best_pos, best_text = -1, ""

    for m in _COND_KEYWORD_PAT.finditer(body, 0, call_offset):
        kw = m.group(1)
        paren_start = m.end() - 1
        depth, paren_end = 0, paren_start
        for i in range(paren_start, min(paren_start + 2000, len(body))):
            if body[i] == '(':
                depth += 1
            elif body[i] == ')':
                depth -= 1
                if depth == 0:
                    paren_end = i
                    break
        if paren_end <= paren_start:
            continue
        brace_start = body.find('{', paren_end)
        if brace_start == -1 or brace_start >= call_offset:
            continue
        d, inside = 0, True
        for i in range(brace_start, call_offset):
            if body[i] == '{':
                d += 1
            elif body[i] == '}':
                d -= 1
                if d == 0:
                    inside = False
                    break
        if not inside:
            continue
        if m.start() > best_pos:
            cond = body[paren_start + 1:paren_end].strip()
            cond = ' '.join(cond.split())
            cond = cond[:77] + "..." if len(cond) > 80 else cond
            best_pos, best_text = m.start(), f"{kw}: {cond}"

    return best_text


_CALL_PAT = re.compile(
    r'(?:'
    r'(?:(\w+)\s*->\s*(\w+))'       # ptr->method    (group 1, 2)
    r'|'
    r'(?:(\w+)\s*\.\s*(\w+))'       # obj.method     (group 3, 4)
    r'|'
    r'(?:(\w+)\s*::\s*(\w+))'       # Class::method  (group 5, 6) — Super::, ClassName::
    r'|'
    r'(\w+)\s*(?=\()'                # standalone     (group 7)
    r')\s*\('
)

def _extract_calls(body: str) -> list[tuple[str, str, str]]:
    clean = _remove_comments(body)

    # 1. Extract delegate bindings before masking (AddDynamic args become invisible after)
    delegates: list[tuple[str, str, str]] = []
    for cls_name, method in _DELEGATE_BIND_PAT.findall(clean):
        delegates.append((cls_name, method, "delegate"))

    # 2. Extract normal calls from masked body
    masked = _masked_body(clean)
    masked = _FUNC_PTR_PAT.sub('', masked)

    calls = []
    for m in _CALL_PAT.finditer(masked):
        if m.group(1) and m.group(2):
            obj, method = m.group(1), m.group(2)
        elif m.group(3) and m.group(4):
            obj, method = m.group(3), m.group(4)
        elif m.group(5) and m.group(6):
            obj, method = m.group(5), m.group(6)
        elif m.group(7):
            obj, method = "", m.group(7)
        else:
            continue

        if method in _IGNORE_CALLS:
            continue
        if any(method.startswith(p) for p in _IGNORE_CLASS_PREFIXES):
            continue
        if len(method) < 2:
            continue
        # Skip ALL_CAPS macros
        if re.match(r'^[A-Z][A-Z0-9_]+$', method):
            continue
        condition = _extract_condition_at(clean, m.start())
        calls.append((obj, method, condition))
    return calls + delegates


def _extract_function_body(cpp_text: str, func_name: str) -> str | None:
    """Extract the body of Class::func_name from a .cpp file."""
    pat = re.compile(
        r'\b\w+\s*::\s*' + re.escape(func_name) + r'\s*\(',
        re.DOTALL,
    )
    m = pat.search(cpp_text)
    if not m:
        return None

    paren_start = cpp_text.index('(', m.start())
    paren_end   = _balanced_paren_end(cpp_text, paren_start)
    brace_pos   = cpp_text.find('{', paren_end)
    if brace_pos == -1:
        return None
    # Detect forward declarations (function prototype followed by ';')
    semi_pos = cpp_text.find(';', paren_end)
    if semi_pos != -1 and semi_pos < brace_pos:
        rest_match = pat.search(cpp_text, m.end())
        if rest_match:
            return _extract_function_body(cpp_text[m.end():], func_name)
        return None

    depth = 0
    for i in range(brace_pos, len(cpp_text)):
        if cpp_text[i] == '{':
            depth += 1
        elif cpp_text[i] == '}':
            depth -= 1
            if depth == 0:
                return cpp_text[brace_pos + 1:i]
    return None


# ── Source file index ─────────────────────────────────────────

_IGNORE_DIRS = {
    "Binaries", "Intermediate", "Saved", "Build",
    ".vs", ".idea", "node_modules", "build", "out",
    "cmake-build-debug", "cmake-build-release",
    "cocos2d",              # Skip Cocos2d-x engine source itself
    "Classes",              # Some Cocos projects separate headers here
}


def _find_cpp_files(source_path: str) -> dict[str, str]:
    """Return {ClassName: cpp_file_path} index by scanning .cpp files."""
    result: dict[str, str] = {}
    for cpp in Path(source_path).rglob("*.cpp"):
        if any(p in _IGNORE_DIRS for p in cpp.parts):
            continue
        try:
            text = cpp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in re.finditer(r'\b([A-Z]\w+)\s*::\s*\w+\s*\(', text):
            cls = m.group(1)
            if cls not in result:
                result[cls] = str(cpp)
    return result


def _build_parent_map(source_path: str) -> dict[str, str]:
    """Scan .h files and return {ChildClass: DirectParentClass} for project classes.

    Used to resolve Super::Method() calls to the actual parent class implementation.
    """
    result: dict[str, str] = {}
    pat = re.compile(
        r'class\s+(?:[A-Z0-9_]+_API\s+)?([AUF][A-Za-z0-9_]+)\s*:\s*public\s+([AUF][A-Za-z0-9_]+)'
    )
    for h in Path(source_path).rglob("*.h"):
        if any(p in _IGNORE_DIRS for p in h.parts):
            continue
        try:
            text = h.read_text(encoding="utf-8", errors="ignore")
            for child, parent in pat.findall(text):
                if child not in result:
                    result[child] = parent
        except Exception:
            continue
    return result


# ── Flow graph data structures ────────────────────────────────

@dataclass
class FlowNode:
    id:          str
    class_name:  str
    method:      str
    is_entry:    bool = False
    is_leaf:     bool = False
    is_dispatch: bool = False  # event / callback boundary


@dataclass
class FlowEdge:
    from_id:      str
    to_id:        str
    context:      str  = ""       # "virtual", "callback", etc.
    is_dynamic:   bool = False
    condition:    str  = ""       # "if: ...", "switch: ...", etc.
    multiplicity: int  = 1        # >1 when same call appears multiple times (e.g. GiveAbility x8)


# ── Core trace logic ──────────────────────────────────────────

def trace_flow(
    source_path:   str,
    class_name:    str,
    method_name:   str,
    max_depth:     int = 5,
    focus_classes: list[str] | None = None,
) -> tuple[list[FlowNode], list[FlowEdge]]:

    cpp_files       = _find_cpp_files(source_path)
    project_classes = set(cpp_files.keys())
    parent_map      = _build_parent_map(source_path)

    # Loose class name lookup: maps prefix-stripped variants to canonical names.
    # e.g. "UARGamePlayAbility_BasicAttack" also registers "ARGamePlayAbility_BasicAttack"
    # so callee_cls resolved from source code (without U/A prefix) still resolves correctly.
    _loose_cls: dict[str, str] = {}
    for c in project_classes:
        _loose_cls[c] = c
        if len(c) > 1 and c[0] in "UAF" and c[1].isupper():
            _loose_cls.setdefault(c[1:], c)

    # Normalize entry class name (in case caller omitted UE prefix)
    class_name = _loose_cls.get(class_name, class_name)

    nodes:       dict[str, FlowNode] = {}
    edges:       list[FlowEdge]      = []
    seen_edges:  set[tuple[str, str]] = set()
    visited_nodes: set[str]           = set()

    def get_cpp_text(cls: str) -> str | None:
        path = cpp_files.get(cls)
        if not path:
            # Loose match: handle name differences like MyClass vs CMyClass
            for key, p in cpp_files.items():
                if cls in key or key in cls:
                    path = p
                    break
        if not path:
            return None
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

    def visit(cls: str, method: str, depth: int, parent_id: str | None,
              condition: str = ""):
        node_id = f"{cls}.{method}"

        if node_id not in nodes:
            nodes[node_id] = FlowNode(
                id=node_id, class_name=cls, method=method,
                is_entry=(parent_id is None),
            )

        if parent_id:
            ek = (parent_id, node_id)
            if ek not in seen_edges:
                seen_edges.add(ek)
                edges.append(FlowEdge(from_id=parent_id, to_id=node_id,
                                      condition=condition))
            else:
                # Same call repeated (e.g. GiveAbility x8): increment multiplicity
                for e in edges:
                    if e.from_id == parent_id and e.to_id == node_id:
                        e.multiplicity += 1
                        break

        if depth <= 0:
            nodes[node_id].is_leaf = True
            return

        if node_id in visited_nodes:
            return
        visited_nodes.add(node_id)

        cpp_text = get_cpp_text(cls)
        if not cpp_text:
            nodes[node_id].is_leaf = True
            return

        body = _extract_function_body(cpp_text, method)
        if not body:
            nodes[node_id].is_leaf = True
            return

        calls = _extract_calls(body)
        if not calls:
            nodes[node_id].is_leaf = True
            return

        for obj, callee, cond in calls:
            callee_cls = cls
            if obj and obj not in ("this", "self"):
                if obj == "Super":
                    # Resolve Super::Method() to the actual C++ parent class
                    callee_cls = parent_map.get(cls, cls)
                elif obj[0].isupper():
                    callee_cls = obj

            callee_id = f"{callee_cls}.{callee}"

            # ── UE5 AbilityTask async pattern ────────────────────
            # CreateXxx/NewAbilityTask on an AbilityTask class → also trace Activate()
            is_task_creation = callee.startswith("Create") or callee in ("NewAbilityTask", "NewObject")
            if is_task_creation and "AbilityTask" in callee_cls:
                visit(callee_cls, "Activate", depth - 1, node_id, cond + " (AbilityTask)")

            # Focus filter: add as leaf if out of focus
            if focus_classes and callee_cls not in focus_classes and callee_cls != cls:
                if callee_id not in nodes:
                    nodes[callee_id] = FlowNode(
                        id=callee_id, class_name=callee_cls,
                        method=callee, is_leaf=True,
                    )
                ek = (node_id, callee_id)
                if ek not in seen_edges:
                    seen_edges.add(ek)
                    edges.append(FlowEdge(from_id=node_id, to_id=callee_id,
                                          condition=cond))
                continue

            # Normalize callee class for UE prefix variations (ARFoo → UARFoo)
            resolved = _loose_cls.get(callee_cls)
            if resolved and resolved != callee_cls:
                callee_cls = resolved
                callee_id  = f"{callee_cls}.{callee}"

            should_recurse = callee_cls in project_classes
            visit(callee_cls, callee,
                  depth - 1 if should_recurse else 0,
                  node_id, cond)

    visit(class_name, method_name, max_depth, None)
    return list(nodes.values()), edges


# ── Public JSON serialisation ─────────────────────────────────

def flow_to_json(
    source_path:   str,
    class_name:    str,
    method_name:   str,
    max_depth:     int = 5,
    focus_classes: list[str] | None = None,
) -> dict:
    nodes, edges = trace_flow(
        source_path, class_name, method_name, max_depth, focus_classes,
    )
    # Use actual entry node (class_name may have been normalized inside trace_flow)
    entry_node  = next((n for n in nodes if n.is_entry), None)
    entry_id    = entry_node.id         if entry_node else f"{class_name}.{method_name}"
    entry_class = entry_node.class_name if entry_node else class_name
    return {
        "entry":      entry_id,
        "entryClass": entry_class,
        "depth":      max_depth,
        "bpBridge":   False,   # No Blueprint concept in plain C++
        "nodes": [
            {
                "id":              n.id,
                "class":           n.class_name,
                "method":          n.method,
                "label":           f"{n.class_name}.{n.method}",
                "isEntry":         n.is_entry,
                "isLeaf":          n.is_leaf,
                "isAsync":         False,
                "isDispatch":      n.is_dispatch,
                "isBlueprintNode": False,
            }
            for n in nodes
        ],
        "edges": [
            {
                "from":         e.from_id,
                "to":           e.to_id,
                "context":      e.context,
                "isDynamic":    e.is_dynamic,
                "condition":    e.condition,
                "multiplicity": e.multiplicity,
            }
            for e in edges
        ],
        "dispatches": [],
    }

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

_DELEGATE_FUNC_NAMES = {
    "bind", "connect", "disconnect", "addEventListenerWithSceneGraphPriority",
    "addEventListenerWithFixedPriority", "addEventListener",
    "schedule", "scheduleOnce", "scheduleUpdate",
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

_CALL_PAT = re.compile(
    r'(?:'
    r'(?:(\w+)\s*->\s*(\w+))'       # ptr->method
    r'|'
    r'(?:(\w+)\s*\.\s*(\w+))'       # obj.method
    r'|'
    r'(\w+)\s*(?=\()'                # standalone function
    r')\s*\('
)

def _extract_calls(body: str) -> list[tuple[str, str]]:
    clean = _remove_comments(body)
    clean = _masked_body(clean)
    clean = _FUNC_PTR_PAT.sub('', clean)

    calls = []
    for m in _CALL_PAT.finditer(clean):
        if m.group(1) and m.group(2):
            obj, method = m.group(1), m.group(2)
        elif m.group(3) and m.group(4):
            obj, method = m.group(3), m.group(4)
        elif m.group(5):
            obj, method = "", m.group(5)
        else:
            continue

        if method in _IGNORE_CALLS:
            continue
        if len(method) < 2:
            continue
        # Skip ALL_CAPS macros
        if re.match(r'^[A-Z][A-Z0-9_]+$', method):
            continue
        calls.append((obj, method))
    return calls


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
    from_id:    str
    to_id:      str
    context:    str  = ""       # "virtual", "callback", etc.
    is_dynamic: bool = False


# ── Core trace logic ──────────────────────────────────────────

def trace_flow(
    source_path:   str,
    class_name:    str,
    method_name:   str,
    max_depth:     int = 3,
    focus_classes: list[str] | None = None,
) -> tuple[list[FlowNode], list[FlowEdge]]:

    cpp_files       = _find_cpp_files(source_path)
    project_classes = set(cpp_files.keys())
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

    def visit(cls: str, method: str, depth: int, parent_id: str | None):
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
                edges.append(FlowEdge(from_id=parent_id, to_id=node_id))

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

        for obj, callee in calls:
            callee_cls = cls
            if obj and obj not in ("this", "self"):
                # Upper-case object names are likely class names / singletons
                if obj[0].isupper():
                    callee_cls = obj

            callee_id = f"{callee_cls}.{callee}"

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
                    edges.append(FlowEdge(from_id=node_id, to_id=callee_id))
                continue

            should_recurse = callee_cls in project_classes and depth > 1
            visit(callee_cls, callee,
                  depth - 1 if should_recurse else 0,
                  node_id)

    visit(class_name, method_name, max_depth, None)
    return list(nodes.values()), edges


# ── Public JSON serialisation ─────────────────────────────────

def flow_to_json(
    source_path:   str,
    class_name:    str,
    method_name:   str,
    max_depth:     int = 3,
    focus_classes: list[str] | None = None,
) -> dict:
    nodes, edges = trace_flow(
        source_path, class_name, method_name, max_depth, focus_classes,
    )
    return {
        "entry":      f"{class_name}.{method_name}",
        "entryClass": class_name,
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
                "from":      e.from_id,
                "to":        e.to_id,
                "context":   e.context,
                "isDynamic": e.is_dynamic,
            }
            for e in edges
        ],
        "dispatches": [],
    }

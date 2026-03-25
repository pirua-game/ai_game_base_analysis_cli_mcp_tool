"""
gdep.ue5_flow
UE5-specific function call flow analyzer.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# ── Identifiers to ignore ─────────────────────────────────────
_IGNORE_CALLS = {
    "if", "for", "while", "switch", "return", "new", "delete",
    "sizeof", "decltype", "static_assert", "nullptr", "true", "false",
    "Super", "Cast", "TEXT", "UE_LOG", "check", "ensure", "verify",
    "checkf", "ensureMsgf", "checkNoEntry",
    "CreateDefaultSubobject", "SetupAttachment",
    "GetSubsystem", "AddMappingContext", "GetLocalPlayer",
    "FGameplayTag", "FGameplayAbilitySpec", "FGameplayEventData",
    "FRotator", "FVector", "FHitResult",
    "INDEX_NONE", "ECC_Visibility",
}

_IGNORE_CLASS_PREFIXES = (
    "std::", "boost::",
    "TArray::", "TMap::", "TSet::", "TQueue::",   # UE5 컨테이너 내부 메서드
    "FString::", "FName::", "FText::",             # UE5 문자열 타입 내부
    "__",                                          # 컴파일러 내부 심볼
)

_DELEGATE_FUNC_NAMES = {
    "BindAction", "BindDelegate", "BindAxis", "BindUFunction",
    "AddDynamic", "AddUFunction", "AddWeakLambda", "AddLambda",
    "RemoveDynamic", "BindRaw",
}

# ── Balanced parenthesis extraction ────────────────────────────────────
def _balanced_paren_end(text, start):
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

# ── Comment removal ────────────────────────────────────────────────
def _remove_comments(text):
    """Removes C/C++ comments (// line comments, /* */ block comments)"""
    result = []
    i = 0
    n = len(text)
    while i < n:
        # Block comments
        if text[i] == '/' and i + 1 < n and text[i+1] == '*':
            end = text.find('*/', i + 2)
            if end == -1:
                break
            i = end + 2
        # Line comments
        elif text[i] == '/' and i + 1 < n and text[i+1] == '/':
            while i < n and text[i] != '\n':
                i += 1
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)

# ── Function body extraction ─────────────────────────────────────────────
def _extract_function_body(cpp_text, func_name):
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
    semi_pos = cpp_text.find(';', paren_end)
    if semi_pos != -1 and semi_pos < brace_pos:
        rest = pat.search(cpp_text, m.end())
        if rest:
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

# ── Delegate masking ───────────────────────────────────────────
def _masked_body(body):
    result = list(body)
    i = 0
    n = len(body)
    while i < n:
        for fname in _DELEGATE_FUNC_NAMES:
            fl = len(fname)
            if body[i:i+fl] == fname:
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

# ── Function pointer removal ──────────────────────────────────────────
_FUNC_PTR_PAT = re.compile(r'&\s*\w+\s*::\s*\w+')

# ── Condition keyword extraction ───────────────────────────────────────
_COND_KEYWORD_PAT = re.compile(r'\b(if|switch|while|for)\s*\(')


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


# ── Direct call extraction ────────────────────────────────────────────
_CALL_PAT = re.compile(
    r'(?:'
    r'(?:(\w+)\s*->\s*(\w+))'
    r'|'
    r'(?:(\w+)\s*\.\s*(\w+))'
    r'|'
    r'(\w+)\s*(?=\()'
    r')\s*\('
)

def _extract_calls(body):
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
        if any(method.startswith(p) for p in _IGNORE_CLASS_PREFIXES):
            continue
        if len(method) < 2:
            continue
        if re.match(r'^[A-Z][A-Z0-9_]+$', method):
            continue
        condition = _extract_condition_at(clean, m.start())
        calls.append((obj, method, condition))
    return calls

# ── Nodes / Edges ───────────────────────────────────────────────
@dataclass
class FlowNode:
    id:          str
    class_name:  str
    method:      str
    is_entry:    bool = False
    is_leaf:     bool = False
    is_dispatch: bool = False

@dataclass
class FlowEdge:
    from_id:    str
    to_id:      str
    context:    str  = ""
    is_dynamic: bool = False
    condition:  str  = ""       # "if: ...", "switch: ...", etc.

# ── Source file collection ────────────────────────────────────────────
_IGNORE_DIRS = {"Binaries","Intermediate","Saved","Build","Content",".vs",".idea"}

def _find_cpp_files(source_path):
    result = {}
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

# ── Flow Analysis ─────────────────────────────────────────────────
def trace_flow(source_path, class_name, method_name,
               max_depth=3, focus_classes=None):
    cpp_files       = _find_cpp_files(source_path)
    project_classes = set(cpp_files.keys())
    nodes           = {}
    edges           = []
    seen_edges      = set()
    visited_nodes   = set()

    # ── BP mapping (best-effort, never blocks flow analysis) ──────
    _bp_map = None
    try:
        from .ue5_blueprint_mapping import build_bp_map
        from .ue5_blueprint_refs import find_content_root
        # Reuse the module-level cache from ue5_runner if available,
        # otherwise fall back to a local build (first call only).
        content_root = find_content_root(source_path)
        if content_root and content_root.exists():
            try:
                from .ue5_runner import _bp_map_cache
                cr_key   = str(content_root)
                cr_mtime = content_root.stat().st_mtime
                cached   = _bp_map_cache.get(cr_key)
                if cached and cached["mtime"] == cr_mtime:
                    _bp_map = cached["bp_map"]
                else:
                    _bp_map = build_bp_map(source_path)
                    _bp_map_cache[cr_key] = {"mtime": cr_mtime, "bp_map": _bp_map}
            except ImportError:
                _bp_map = build_bp_map(source_path)
    except Exception:
        pass

    def _inject_bp_chain(cpp_cls: str, k2_method: str, parent_id: str):
        """Inject BP event node + call_chain after a K2_ virtual boundary."""
        if _bp_map is None:
            return
        candidates = [cpp_cls]
        for prefix in ('A', 'U', 'F', 'I', 'E'):
            if cpp_cls.startswith(prefix):
                candidates.append(cpp_cls[1:])
            else:
                candidates.append(prefix + cpp_cls)
        injected: set[str] = set()
        for c in candidates:
            for bm in _bp_map.cpp_to_bps.get(c, []):
                if bm.bp_class in injected:
                    continue
                for ev in bm.event_nodes:
                    if ev.name != k2_method:
                        continue
                    injected.add(bm.bp_class)
                    bp_id = f"{bm.bp_class}.{k2_method}"
                    if bp_id not in nodes:
                        nodes[bp_id] = FlowNode(
                            id=bp_id,
                            class_name=bm.bp_class,
                            method=k2_method,
                            is_entry=False,
                            is_leaf=not ev.call_chain,
                            is_dispatch=True,
                        )
                    ek = (parent_id, bp_id)
                    if ek not in seen_edges:
                        seen_edges.add(ek)
                        edges.append(FlowEdge(
                            from_id=parent_id, to_id=bp_id,
                            context="blueprint", is_dynamic=True,
                        ))
                    prev_id = bp_id
                    for fn in ev.call_chain[:8]:
                        fn_id = f"{bm.bp_class}.[BP]{fn}"
                        if fn_id not in nodes:
                            nodes[fn_id] = FlowNode(
                                id=fn_id,
                                class_name=bm.bp_class,
                                method=f"[BP]{fn}",
                                is_leaf=True,
                            )
                        ek2 = (prev_id, fn_id)
                        if ek2 not in seen_edges:
                            seen_edges.add(ek2)
                            edges.append(FlowEdge(
                                from_id=prev_id, to_id=fn_id,
                                context="bp_call",
                            ))
                        prev_id = fn_id
                    break  # one event match per BP is enough

    def get_cpp_text(cls):
        path = cpp_files.get(cls)
        if not path:
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

    def visit(cls, method, depth, parent_id, condition=""):
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
        if depth <= 0:
            nodes[node_id].is_leaf = True
            return
        if node_id in visited_nodes:
            return
        visited_nodes.add(node_id)
        cpp_text = get_cpp_text(cls)
        if not cpp_text:
            nodes[node_id].is_leaf = True
            # K2_ virtual with no C++ body → inject BP implementation
            if method.startswith('K2_'):
                _inject_bp_chain(cls, method, node_id)
            return
        body = _extract_function_body(cpp_text, method)
        if not body:
            nodes[node_id].is_leaf = True
            if method.startswith('K2_'):
                _inject_bp_chain(cls, method, node_id)
            return
        calls = _extract_calls(body)
        if not calls:
            nodes[node_id].is_leaf = True
            return
        for obj, callee, cond in calls:
            callee_cls = cls
            if obj and obj not in ("this", "Super", "self"):
                if obj[0].isupper():
                    callee_cls = obj
            callee_id = f"{callee_cls}.{callee}"
            if focus_classes and callee_cls not in focus_classes and callee_cls != cls:
                if callee_id not in nodes:
                    nodes[callee_id] = FlowNode(
                        id=callee_id, class_name=callee_cls, method=callee, is_leaf=True,
                    )
                ek = (node_id, callee_id)
                if ek not in seen_edges:
                    seen_edges.add(ek)
                    edges.append(FlowEdge(from_id=node_id, to_id=callee_id,
                                          condition=cond))
                continue
            should_recurse = callee_cls in project_classes and depth > 1
            visit(callee_cls, callee, depth - 1 if should_recurse else 0, node_id, cond)
            # If this callee is a K2_ method and became a leaf, inject BP chain
            callee_node_id = f"{callee_cls}.{callee}"
            if (callee.startswith('K2_')
                    and callee_node_id in nodes
                    and nodes[callee_node_id].is_leaf):
                _inject_bp_chain(callee_cls, callee, callee_node_id)

    # GAS ability bridge: C++ ActivateAbility/etc → BP K2_ActivateAbility/etc
    _K2_BRIDGE_MAP = {
        "ActivateAbility":  "K2_ActivateAbility",
        "EndAbility":       "K2_OnEndAbility",
        "ActivateAbilityFromEvent": "K2_ActivateAbilityFromEvent",
    }

    visit(class_name, method_name, max_depth, None)

    # Post-visit: if entry method has a K2_ equivalent and BP implements it,
    # inject BP bridge from the entry node
    k2_equiv = _K2_BRIDGE_MAP.get(method_name)
    if k2_equiv:
        entry_id = f"{class_name}.{method_name}"
        _inject_bp_chain(class_name, k2_equiv, entry_id)

    return list(nodes.values()), edges


def flow_to_json(source_path, class_name, method_name,
                 max_depth=3, focus_classes=None):
    nodes, edges = trace_flow(
        source_path, class_name, method_name, max_depth, focus_classes
    )
    # Detect if any BP bridge nodes were injected
    has_bp_bridge = any(n.is_dispatch and n.class_name.endswith('_C')
                        for n in nodes)
    return {
        "entry":      f"{class_name}.{method_name}",
        "entryClass": class_name,
        "depth":      max_depth,
        "bpBridge":   has_bp_bridge,
        "nodes": [
            {
                "id":         n.id,
                "class":      n.class_name,
                "method":     n.method,
                "label":      (f"[BP] {n.class_name}.{n.method}"
                               if n.is_dispatch and n.class_name.endswith('_C')
                               else f"{n.class_name}.{n.method}"),
                "isEntry":    n.is_entry,
                "isLeaf":     n.is_leaf,
                "isAsync":    False,
                "isDispatch": n.is_dispatch,
                "isBlueprintNode": n.class_name.endswith('_C'),
            }
            for n in nodes
        ],
        "edges": [
            {
                "from":      e.from_id,
                "to":        e.to_id,
                "context":   e.context,
                "isDynamic": e.is_dynamic,
                "condition": e.condition,
            }
            for e in edges
        ],
        "dispatches": [],
    }

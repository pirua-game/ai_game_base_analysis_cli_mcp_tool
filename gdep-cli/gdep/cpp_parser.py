"""
gdep.cpp_parser
Data classes and analysis utilities for standard C++ projects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Ignored Directories ──────────────────────────────────────
_IGNORE_DIRS = {
    "build", "bin", "obj", "Debug", "Release",
    ".git", ".vs", ".idea", ".vscode",
    "third_party", "external", "lib", "vendor",
}

# ── C++ Basic Types and STL ──────────────────────────────────
CPP_BASIC_TYPES = {
    "int", "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "float", "double", "bool", "void", "char", "wchar_t", "size_t",
    "std::string", "std::wstring", "std::vector", "std::map", "std::set",
    "std::list", "std::deque", "std::stack", "std::queue", "std::priority_queue",
    "std::pair", "std::tuple", "std::shared_ptr", "std::unique_ptr", "std::weak_ptr",
    "std::optional", "std::variant", "std::any", "std::function",
    "int8_t", "int16_t", "int32_t", "int64_t",
    "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "auto", "nullptr_t",
}

# ── Data Classes ─────────────────────────────────────────────

@dataclass
class CPPProperty:
    name:          str
    type_:         str
    access:        str       = "public"
    is_static:     bool      = False
    is_const:      bool      = False


@dataclass
class CPPFunction:
    name:         str
    return_type:  str       = "void"
    params:       list[str] = field(default_factory=list)
    access:       str       = "public"
    is_virtual:   bool      = False
    is_static:    bool      = False
    is_const:     bool      = False
    is_override:  bool      = False


@dataclass
class CPPClass:
    name:         str
    kind:         str               # class / struct
    bases:        list[str]         = field(default_factory=list)
    properties:   list[CPPProperty] = field(default_factory=list)
    functions:    list[CPPFunction] = field(default_factory=list)
    dependencies: list[str]         = field(default_factory=list) # For --deep mode
    enum_values:  list[str]         = field(default_factory=list)
    source_file:  str               = ""
    namespace:    str               = ""


@dataclass
class CPPProject:
    root:    Path
    classes: dict[str, CPPClass] = field(default_factory=dict)
    structs: dict[str, CPPClass] = field(default_factory=dict)
    enums:   dict[str, CPPClass] = field(default_factory=dict)


# ── Analysis Utilities ───────────────────────────────────────

def _normalize_type(t: str) -> str:
    if not t: return ""
    t = t.strip()
    # Remove comments
    t = re.sub(r'//.*', '', t)
    # Remove prefixes
    t = re.sub(r'\b(const|class|struct|enum|static|volatile|virtual)\b', '', t).strip()
    # Handle templates (std::vector<MyClass*> -> MyClass)
    m = re.search(r'<([^>]+)>', t)
    if m:
        inner = m.group(1).split(',')[0].strip()
        return _normalize_type(inner)
    # Remove pointers/references
    t = t.replace('*', '').replace('&', '').strip()
    # Remove namespace (std::string -> string)
    # Note: std:: prefix might be needed for CPP_BASIC_TYPES identification,
    # but here we extract only the last element.
    t = t.split('::')[-1].strip()
    return t

def compute_coupling(proj: CPPProject) -> list[dict]:
    all_items = {**proj.classes, **proj.structs}
    counts: dict[str, int] = {name: 0 for name in all_items}

    for cls in all_items.values():
        # 1. Inheritance
        for b in cls.bases:
            t = _normalize_type(b)
            if t in counts: counts[t] += 1

        # 2. Properties
        for p in cls.properties:
            t = _normalize_type(p.type_)
            if t in counts: counts[t] += 1

        # 3. Behavioral Dependencies
        for d in cls.dependencies:
            t = _normalize_type(d)
            if t in counts: counts[t] += 1

    result = []
    for name, score in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        cls = all_items.get(name)
        result.append({
            "name": name,
            "score": score,
            "file": Path(cls.source_file).name if cls else "Unknown",
            "full_path": cls.source_file if cls else ""
        })
    return result

def find_cycles(proj: CPPProject) -> list[str]:
    all_items = {**proj.classes, **proj.structs}
    cycles = []
    visited = set()

    def dfs(name: str, path: list[str]):
        if name in path:
            idx = path.index(name)
            cycles.append(" → ".join(path[idx:] + [name]))
            return
        if name in visited or name not in all_items:
            return
        visited.add(name)
        for b in all_items[name].bases:
            dfs(b, path + [name])

    for name in list(all_items.keys()):
        dfs(name, [])
    return list(dict.fromkeys(cycles))

def to_class_map(proj: CPPProject) -> dict:
    result = {}
    for name, cls in {**proj.classes, **proj.structs, **proj.enums}.items():
        result[name] = {
            "kind":   cls.kind,
            "bases":  cls.bases,
            "fields": [
                {
                    "name":   p.name,
                    "type":   p.type_,
                    "access": p.access,
                    "static": p.is_static,
                    "const":  p.is_const,
                }
                for p in cls.properties
            ],
            "methods": [
                {
                    "name":     f.name,
                    "ret":      f.return_type,
                    "params":   f.params,
                    "access":   f.access,
                    "virtual":  f.is_virtual,
                    "static":   f.is_static,
                    "const":    f.is_const,
                    "override": f.is_override,
                }
                for f in cls.functions
            ],
            "enum_values": cls.enum_values,
            "namespace":   cls.namespace,
        }
    return result

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Union


# We reuse the normalize_type logic from the parsers.
# Since we don't want to create circular imports or depend on a specific parser,
# we'll implement a robust one here or pass it in.
def normalize_type(t: str) -> str:
    if not t: return ""
    t = t.strip()
    # Remove 'class ', 'struct ', 'enum ' prefixes
    t = re.sub(r'^(class|struct|enum)\s+', '', t)
    # Extract inner type from templates like TObjectPtr<T>, std::vector<T>
    m = re.search(r'<(.*)>', t)
    if m:
        inner = m.group(1).split(',')[0].strip()
        return normalize_type(inner)
    # Remove const, pointer, and reference symbols
    t = re.sub(r'\bconst\b', '', t).strip()
    t = t.replace('*', '').replace('&', '').strip()
    # Remove namespaces
    t = t.split('::')[-1].strip()
    return t

class ImpactAnalyzer:
    def __init__(self, project: Any):
        self.project = project
        self.reverse_deps: dict[str, set[str]] = {}
        self.external_files: dict[str, str] = {}
        self._build_reverse_map()

    def _build_reverse_map(self):
        """
        Builds a map where key is a class name and value is a set of classes that depend on it.
        """
        all_items = {}
        if hasattr(self.project, 'classes'):
            all_items.update(self.project.classes)
        if hasattr(self.project, 'structs'):
            all_items.update(self.project.structs)

        for name, cls in all_items.items():
            # 1. Bases (Inheritance)
            for base in cls.bases:
                self._add_rev(base, name)

            # 2. Properties (Composition/Aggregation)
            for prop in cls.properties:
                t = normalize_type(prop.type_)
                if t and t != name:
                    self._add_rev(t, name)

            # 3. Dependencies (from Deep analysis)
            if hasattr(cls, 'dependencies'):
                for dep in cls.dependencies:
                    if dep and dep != name:
                        self._add_rev(dep, name)

    def add_external_impact(self, provider: str, consumer: str, consumer_file: str):
        """
        Manually inject an external dependency (e.g. from a Blueprint/Prefab).
        """
        if provider == consumer:
            return
        self._add_rev(provider, consumer)
        self.external_files[consumer] = consumer_file

    def _add_rev(self, provider: str, consumer: str):
        if provider not in self.reverse_deps:
            self.reverse_deps[provider] = set()
        self.reverse_deps[provider].add(consumer)

    def trace_impact(self, target_class: str, max_depth: int = 3) -> dict[str, Any]:
        """
        BFS to find all classes affected by the target_class.
        Returns a tree-like structure.
        """
        visited = set()
        return self._trace_recursive(target_class, 0, max_depth, visited)

    def _trace_recursive(self, current: str, depth: int, max_depth: int, visited: set[str]) -> dict[str, Any]:
        # Find the class object if it exists in the project to get its file path
        source_file = self.external_files.get(current, "")
        if not source_file:
            all_items = {}
            if hasattr(self.project, 'classes'):
                all_items.update(self.project.classes)
            if hasattr(self.project, 'structs'):
                all_items.update(self.project.structs)

            if current in all_items:
                source_file = all_items[current].source_file

        node = {
            "name": current,
            "file": source_file,
            "children": []
        }

        if depth >= max_depth or current in visited:
            return node

        visited.add(current)

        impacted_classes = sorted(list(self.reverse_deps.get(current, set())))
        for impacted in impacted_classes:
            child_node = self._trace_recursive(impacted, depth + 1, max_depth, visited)
            node["children"].append(child_node)

        return node

    def format_as_tree(self, node: dict[str, Any], prefix: str = "", is_last: bool = True, is_root: bool = True) -> list[str]:
        lines = []

        # Current node
        if is_root:
            line = f"{node['name']}"
        else:
            marker = "└── " if is_last else "├── "
            line = f"{prefix}{marker}{node['name']}"

        if node['file']:
            line += f" ({node['file']})"

        lines.append(line)

        # Children
        children = node.get("children", [])

        # New prefix for children
        if is_root:
            new_prefix = ""
        else:
            new_prefix = prefix + ("    " if is_last else "│   ")

        for i, child in enumerate(children):
            is_child_last = (i == len(children) - 1)
            lines.extend(self.format_as_tree(child, new_prefix, is_child_last, is_root=False))

        return lines

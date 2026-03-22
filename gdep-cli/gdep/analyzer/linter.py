"""
gdep.analyzer.linter
Game-Specific Anti-pattern Scanner (Linter)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..ue5_parser import UE5Class, UE5Function, UE5Project

@dataclass
class LintResult:
    rule_id: str
    severity: str  # "Error", "Warning", "Info"
    message: str
    class_name: str
    method_name: str = ""
    file_path: str = ""
    suggestion: str = ""

class Linter:
    def __init__(self):
        self.results: list[LintResult] = []

    def lint_ue5(self, project: UE5Project) -> list[LintResult]:
        self.results = []
        for cls_name, cls in project.classes.items():
            self._check_ue5_heavy_lifecycle(cls)
            self._check_ue5_missing_super(cls)
            self._check_ue5_gas_patterns(cls)
            self._check_ue5_ufunction_overuse(cls)
            self._check_ue5_replication(cls)

        self._check_circular_dependencies(project)
        return self.results

    def _check_ue5_heavy_lifecycle(self, cls: UE5Class):
        """[UE5] Check for heavy operations in Tick or BeginPlay."""
        heavy_ops = [
            (r"\bSpawnActor\b", "Actor Spawning"),
            (r"\bNewObject\b", "Object Allocation"),
            (r"\bFindObject\b", "Object Lookup"),
            (r"\bLoadObject\b", "Synchronous Loading"),
            (r"\bGetAllActorsOfClass\b", "Heavy Iterator"),
        ]

        for func in cls.functions:
            # Debug: show what we're scanning
            # print(f"[debug] Linting {cls.name}.{func.name} (body: {len(func.body_text) if func.body_text else 0} chars)")

            if not func.body_text:
                continue

            f_name_lower = func.name.lower()

            # Tick detection: robust check for "Tick" in name
            if "tick" in f_name_lower:
                for pattern, op_name in heavy_ops:
                    if re.search(pattern, func.body_text):
                        self.results.append(LintResult(
                            rule_id="UE5-PERF-001",
                            severity="Error",
                            message=f"Heavy operation '{op_name}' detected in Tick().",
                            class_name=cls.name,
                            method_name=func.name,
                            file_path=func.source_file or cls.source_file,
                            suggestion="Move this operation to BeginPlay or use a timer/delegate."
                        ))

            # BeginPlay is less critical but still worth checking for sync loads
            elif "beginplay" in f_name_lower or "nativeconstruct" in f_name_lower:
                if "LoadObject" in func.body_text:
                    self.results.append(LintResult(
                        rule_id="UE5-PERF-002",
                        severity="Warning",
                        message="Synchronous LoadObject detected in BeginPlay().",
                        class_name=cls.name,
                        method_name=func.name,
                        file_path=func.source_file or cls.source_file,
                        suggestion="Consider using TSoftObjectPtr and AsyncLoad."
                    ))

    def _check_ue5_missing_super(self, cls: UE5Class):
        """[UE5] Check for missing Super:: call in overridden lifecycle methods."""
        lifecycle_overrides = ["BeginPlay", "EndPlay", "Tick", "OnConstruction"]

        for func in cls.functions:
            is_lifecycle_method = func.name in lifecycle_overrides
            if not (is_lifecycle_method and func.body_text):
                continue
            super_call = f"Super::{func.name}"
            if super_call not in func.body_text:
                self.results.append(LintResult(
                    rule_id="UE5-BASE-001",
                    severity="Warning",
                    message=f"Possible missing {super_call} call in lifecycle method.",
                    class_name=cls.name,
                    method_name=func.name,
                    file_path=func.source_file or cls.source_file,
                    suggestion=f"Ensure {super_call}(...) is called to maintain engine logic."
                ))

    def _check_ue5_gas_patterns(self, cls: UE5Class):
        """[UE5-GAS] GAS-specific anti-pattern checks."""
        # Only check classes that inherit from UGameplayAbility
        is_ability = any(
            "GameplayAbility" in b or "UGameplayAbility" in b
            for b in cls.bases
        )
        if not is_ability:
            return

        for func in cls.functions:
            if not func.body_text:
                continue
            body = func.body_text

            # UE5-GAS-001: ActivateAbility without CommitAbility
            if func.name in ("ActivateAbility", "K2_ActivateAbility"):
                if "CommitAbility" not in body and "CommitAbilityChecked" not in body:
                    self.results.append(LintResult(
                        rule_id="UE5-GAS-001",
                        severity="Warning",
                        message=f"{func.name}() does not call CommitAbility(). "
                                f"Costs (cooldown/resources) will not be applied.",
                        class_name=cls.name,
                        method_name=func.name,
                        file_path=func.source_file or cls.source_file,
                        suggestion="Add CommitAbility(Handle, ActorInfo, ActivationInfo) "
                                   "before applying effects. Call EndAbility if commit fails."
                    ))

            # UE5-GAS-002: Expensive world queries inside Ability methods
            expensive_calls = [
                (r"\bGetAllActorsOfClass\b", "GetAllActorsOfClass"),
                (r"\bUGameplayStatics::GetAllActors\b", "GetAllActors"),
                (r"\bFindObject<\b", "FindObject"),
                (r"\bLoadObject<\b", "Synchronous LoadObject"),
            ]
            for pattern, op_name in expensive_calls:
                if re.search(pattern, body):
                    self.results.append(LintResult(
                        rule_id="UE5-GAS-002",
                        severity="Warning",
                        message=f"Expensive world query '{op_name}' in Ability method "
                                f"{func.name}(). GAS Abilities may fire frequently.",
                        class_name=cls.name,
                        method_name=func.name,
                        file_path=func.source_file or cls.source_file,
                        suggestion="Cache the result in BeginPlay or use a dedicated "
                                   "subsystem/manager instead of querying every activation."
                    ))

    def _check_ue5_ufunction_overuse(self, cls: UE5Class):
        """[UE5-GAS-003] Detect methods with BlueprintCallable/Pure that expose too much."""
        # Count functions that have Blueprint-exposing specifiers
        bp_callable_count = 0
        bp_pure_count = 0
        for func in cls.functions:
            specs_lower = [s.lower() for s in func.specifiers]
            if "blueprintcallable" in specs_lower:
                bp_callable_count += 1
            if "blueprintpure" in specs_lower:
                bp_pure_count += 1

        # Heuristic: >10 BlueprintCallable on a single class is suspicious
        if bp_callable_count > 10:
            self.results.append(LintResult(
                rule_id="UE5-GAS-003",
                severity="Info",
                message=f"{bp_callable_count} BlueprintCallable methods on '{cls.name}'. "
                        f"High Blueprint exposure may indicate missing separation of concerns.",
                class_name=cls.name,
                file_path=cls.source_file,
                suggestion="Consider splitting into smaller classes or using a "
                           "BlueprintFunctionLibrary for stateless helpers."
            ))

        # BlueprintPure without const is a common mistake (UE5 enforces this at compile time
        # but gdep can flag it as an early warning)
        for func in cls.functions:
            specs_lower = [s.lower() for s in func.specifiers]
            if "blueprintpure" in specs_lower:
                full_text = (func.body_text or "") + func.return_type
                if "const" not in full_text and func.return_type not in ("void", ""):
                    self.results.append(LintResult(
                        rule_id="UE5-GAS-004",
                        severity="Info",
                        message=f"BlueprintPure method '{func.name}' may be missing "
                                f"'const' qualifier.",
                        class_name=cls.name,
                        method_name=func.name,
                        file_path=func.source_file or cls.source_file,
                        suggestion="BlueprintPure functions should be declared const "
                                   "to prevent accidental state modification."
                    ))

    def _check_ue5_replication(self, cls: UE5Class):
        """[UE5-NET-001] Replicated properties should prefer ReplicatedUsing for callbacks."""
        for prop in cls.properties:
            if not prop.is_replicated:
                continue
            specs_lower = [s.lower() for s in prop.specifiers]
            has_using = any("replicatedusing" in s for s in specs_lower)
            if not has_using and prop.type_ not in ("bool", "float", "int32", "uint8"):
                self.results.append(LintResult(
                    rule_id="UE5-NET-001",
                    severity="Info",
                    message=f"Replicated property '{prop.name}' ({prop.type_}) has no "
                            f"ReplicatedUsing callback. Changes may go unnoticed on clients.",
                    class_name=cls.name,
                    file_path=cls.source_file,
                    suggestion="Add ReplicatedUsing=OnRep_PropertyName and implement "
                               "the callback to react to network updates."
                ))

    def _check_circular_dependencies(self, project: Any):
        """General check for circular dependencies."""
        from ..ue5_parser import find_cycles

        # find_cycles returns list of "A -> B -> A" strings
        cycles = find_cycles(project)
        for cycle in cycles:
            parts = cycle.split(" → ")
            self.results.append(LintResult(
                rule_id="GEN-ARCH-001",
                severity="Warning",
                message=f"Circular dependency detected: {cycle}",
                class_name=parts[0],
                suggestion="Refactor using Interfaces or Delegates to break the cycle."
            ))

    def lint_unity(self, csharp_results: list[dict],
                   source_path: str | None = None) -> list[LintResult]:
        """
        Process linting results from gdep.exe for Unity/C#.
        Also performs Python-side Coroutine / async pattern checks if source_path given.
        """
        unity_results = []
        for r in csharp_results:
            unity_results.append(LintResult(
                rule_id=r.get("ruleId", "CS-LINT"),
                severity=r.get("severity", "Warning"),
                message=r.get("message", ""),
                class_name=r.get("class", ""),
                method_name=r.get("method", ""),
                file_path=r.get("file", ""),
                suggestion=r.get("suggestion", "")
            ))

        # Python-side Unity checks (coroutine patterns)
        if source_path:
            unity_results.extend(self._check_unity_coroutine_patterns(source_path))

        return unity_results

    def _check_unity_coroutine_patterns(self, source_path: str) -> list[LintResult]:
        """
        [UNI-ASYNC] Scan C# source files for Coroutine anti-patterns.
        Runs Python-side (no C# toolchain needed).
        """
        import os
        from pathlib import Path

        results: list[LintResult] = []
        src_root = Path(source_path)

        # Regex patterns
        _re_ienumerator = re.compile(
            r'IEnumerator\s+(\w+)\s*\([^)]*\)\s*\{([\s\S]*?)(?=\n\s{0,4}(?:public|private|protected|internal|\}|\/\/))',
            re.MULTILINE
        )
        _re_while_true   = re.compile(r'while\s*\(\s*true\s*\)\s*\{([\s\S]*?)(?=\n\s{0,8}\})', re.MULTILINE)
        _re_yield_inside = re.compile(r'\byield\b')
        _re_heavy_in_co  = re.compile(
            r'\b(FindObjectOfType|FindObjectsOfType|Resources\.Load|'
            r'Resources\.LoadAll|GameObject\.Find)\b'
        )
        _re_class = re.compile(r'(?:class|struct)\s+(\w+)')

        for cs_file in src_root.rglob("*.cs"):
            try:
                text = cs_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            # Detect class name for this file
            cm = _re_class.search(text)
            cls_name = cm.group(1) if cm else cs_file.stem

            # UNI-ASYNC-001: while(true) in Coroutine without yield
            for m in _re_ienumerator.finditer(text):
                method_name = m.group(1)
                body        = m.group(2)

                # UNI-ASYNC-001: while(true) block with no yield INSIDE the loop
                for wm in _re_while_true.finditer(body):
                    loop_body = wm.group(1)
                    if not _re_yield_inside.search(loop_body):
                        results.append(LintResult(
                            rule_id="UNI-ASYNC-001",
                            severity="Error",
                            message=f"IEnumerator '{method_name}' has while(true) with no "
                                    f"yield inside the loop — will hang the Unity main thread.",
                            class_name=cls_name,
                            method_name=method_name,
                            file_path=str(cs_file),
                            suggestion="Add 'yield return null' or 'yield return new WaitForSeconds(...)' "
                                       "inside the while(true) loop body."
                        ))
                        break  # one warning per method is enough

                # UNI-ASYNC-002: Heavy API calls inside Coroutine
                for hm in _re_heavy_in_co.finditer(body):
                    op_name = hm.group(1)
                    results.append(LintResult(
                        rule_id="UNI-ASYNC-002",
                        severity="Warning",
                        message=f"Heavy Unity API '{op_name}' called inside Coroutine "
                                f"'{method_name}'. This runs on the main thread every frame.",
                        class_name=cls_name,
                        method_name=method_name,
                        file_path=str(cs_file),
                        suggestion=f"Cache the result of {op_name} in Start/Awake and "
                                   f"reference the cached value inside the Coroutine."
                    ))

        return results

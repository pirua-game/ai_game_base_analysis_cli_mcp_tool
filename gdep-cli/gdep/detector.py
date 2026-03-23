"""
gdep.detector
Scans project roots to determine engine, framework, and language.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path


class ProjectKind(Enum):
    UNITY       = "unity"
    DOTNET      = "dotnet"
    UNREAL      = "unreal"
    CPP         = "cpp"
    PYTHON      = "python"
    REACT       = "react"
    UNKNOWN     = "unknown"


@dataclass
class ProjectProfile:
    kind:         ProjectKind
    root:         Path
    name:         str
    language:     str              # Primary language
    engine:       str | None       # Engine/Framework name
    version_hint: str | None       # Detected version hint
    source_dirs:  list[Path]       # Candidates for source code paths
    extra:        dict = field(default_factory=dict)  # Additional metadata

    @property
    def display(self) -> str:
        parts = [self.kind.value.upper()]
        if self.engine:     parts.append(self.engine)
        if self.language:   parts.append(f"({self.language})")
        return " · ".join(parts)

    def to_dict(self) -> dict:
        return {
            "kind":         self.kind.value,
            "name":         self.name,
            "root":         str(self.root),
            "language":     self.language,
            "engine":       self.engine,
            "version_hint": self.version_hint,
            "source_dirs":  [str(p) for p in self.source_dirs],
            "extra":        self.extra,
        }


# ── Detection Rules ─────────────────────────────────────────────────

def _find_project_root(start: Path) -> Path:
    """
    Starting from the given path, traverses up to find the project root
    (Unity, Unreal, .NET, etc.). Returns the original path if not found.
    """
    current = start.resolve()
    for _ in range(6):  # Traverse up to 6 levels
        top_files = {f.name for f in current.iterdir() if f.is_file()} if current.is_dir() else set()
        top_dirs  = {d.name for d in current.iterdir() if d.is_dir()}  if current.is_dir() else set()
        # Unity root detection
        if {"Assets", "ProjectSettings"}.issubset(top_dirs):
            return current
        # Unreal root detection
        if any(f.endswith(".uproject") for f in top_files):
            return current
        # .NET solution root detection
        if any(f.endswith(".sln") for f in top_files):
            return current
        # Axmol root detection (ax/ dir or CMakeLists.txt with 'axmol')
        if "ax" in top_dirs:
            return current
        if "CMakeLists.txt" in top_files:
            try:
                cmake_text = (current / "CMakeLists.txt").read_text(
                    encoding="utf-8", errors="replace"
                )[:4096]
                if "axmol" in cmake_text.lower():
                    return current
            except Exception:
                pass
        parent = current.parent
        if parent == current:
            break
        current = parent
    return start.resolve()


def detect(path: str | Path) -> ProjectProfile:
    """
    Detects the project type from the given path.
    Traverses up to find the root even if a subfolder (like Assets/Scripts) is provided.
    Priority: Unity > Unreal > .NET > C++ > Python > React > Unknown
    """
    given = Path(path).resolve()

    # Automatically traverse up to 6 levels to find the project root
    root = _find_project_root(given)

    # File structure snapshot (root + 1 level down)
    top_files  = {f.name for f in root.iterdir() if f.is_file()} if root.is_dir() else set()
    top_dirs   = {d.name for d in root.iterdir() if d.is_dir()}  if root.is_dir() else set()
    all_exts   = _collect_extensions(root, max_depth=2)

    # ── Unity ───────────────────────────────────────────────
    if _is_unity(root, top_dirs, top_files):
        assets_dir  = root / "Assets"
        scripts_dir = assets_dir / "Scripts"

        # If the provided path is under Assets, use it as the primary source path
        if given != root and given.is_dir() and str(given).startswith(str(assets_dir)):
            src_dirs = [given]
        else:
            src_dirs = [scripts_dir if scripts_dir.exists() else assets_dir]

        # Read version from ProjectSettings/ProjectVersion.txt
        version_hint = _read_unity_version(root)
        engine_name = f"Unity {version_hint}" if version_hint else "Unity"

        return ProjectProfile(
            kind=ProjectKind.UNITY,
            root=root,
            name=root.name,
            language="C#",
            engine=engine_name,
            version_hint=version_hint,
            source_dirs=src_dirs,
            extra={"has_packages": (root / "Packages").exists()},
        )

    # ── Axmol Early Detection (ax/ dir or CMakeLists.txt with 'axmol') ────
    if _is_axmol(root, top_files, top_dirs):
        classes_dir = root / "Classes"
        if given != root and given.is_dir() and str(given).startswith(str(root)):
            src_dirs = [given]
        elif classes_dir.exists():
            src_dirs = [classes_dir]
        else:
            src_dirs = [root]
        version_hint = _read_axmol_version(root)
        return ProjectProfile(
            kind=ProjectKind.CPP,
            root=root,
            name=root.name,
            language="C++",
            engine=f"Axmol{' ' + version_hint if version_hint else ''}",
            version_hint=version_hint,
            source_dirs=src_dirs,
            extra={"is_axmol": True},
        )

    # ── Cocos2d-x Early Detection (Classes/ + cocos2d/ combo) ──────
    # Perform this before .NET check to avoid false positives with .sln files
    classes_dir = root / "Classes"
    cocos_dir   = root / "cocos2d"
    if classes_dir.exists() and cocos_dir.exists():
        version_hint = _read_cocos_version(root)
        engine = f"Cocos2d-x{' ' + version_hint if version_hint else ''}"
        if given != root and given.is_dir() and str(given).startswith(str(root)):
            src_dirs = [given]
        else:
            src_dirs = [classes_dir]
        return ProjectProfile(
            kind=ProjectKind.CPP,
            root=root,
            name=root.name,
            language="C++",
            engine=engine,
            version_hint=version_hint,
            source_dirs=src_dirs,
            extra={"is_cocos": True},
        )

    # ── Unreal Engine ────────────────────────────────────────
    if _is_unreal(root, top_files, all_exts):
        uproject = next(root.glob("*.uproject"), None)
        src_dir  = root / "Source"
        src_dirs = [src_dir] if src_dir.exists() else [root]
        version_hint = _read_unreal_version(root)
        return ProjectProfile(
            kind=ProjectKind.UNREAL,
            root=root,
            name=uproject.stem if uproject else root.name,
            language="C++",
            engine=f"Unreal Engine{' ' + version_hint if version_hint else ''}",
            version_hint=version_hint,
            source_dirs=src_dirs,
            extra={"has_blueprints": (root / "Content").exists()},
        )

    # ── .NET (C#) ────────────────────────────────────────────
    if _is_dotnet(root, top_files, all_exts):
        csproj_files = list(root.rglob("*.csproj"))
        src_dir = root / "src"
        src_dirs = [src_dir] if src_dir.exists() else [root]
        version_hint = _read_dotnet_target(csproj_files[0]) if csproj_files else None
        return ProjectProfile(
            kind=ProjectKind.DOTNET,
            root=root,
            name=csproj_files[0].stem if csproj_files else root.name,
            language="C#",
            engine=".NET",
            version_hint=version_hint,
            source_dirs=src_dirs,
        )

    # ── C++ (Generic / Cocos2d-x) ───────────────────────────────
    if _is_cpp(root, top_files, all_exts):
        classes_dir = root / "Classes"
        src_dir     = root / "src"
        source_dir  = root / "Source"

        # If already a sub-path, use it directly
        if given != root and given.is_dir() and str(given).startswith(str(root)):
            src_dirs = [given]
        elif classes_dir.exists():
            src_dirs = [classes_dir]    # Cocos2d-x
        elif src_dir.exists():
            src_dirs = [src_dir]
        elif source_dir.exists():
            src_dirs = [source_dir]
        else:
            src_dirs = [root]

        is_cocos     = (root / "cocos2d").exists()
        version_hint = _read_cocos_version(root) if is_cocos else None
        engine       = "Cocos2d-x" if is_cocos else "C++"

        return ProjectProfile(
            kind=ProjectKind.CPP,
            root=root,
            name=root.name,
            language="C++",
            engine=f"{engine}{' ' + version_hint if version_hint else ''}",
            version_hint=version_hint,
            source_dirs=src_dirs,
            extra={"is_cocos": is_cocos},
        )

    # ── Python ───────────────────────────────────────────────
    if _is_python(root, top_files):
        src_dirs = [root / "src"] if (root / "src").exists() else [root]
        framework = _detect_python_framework(root, top_files)
        return ProjectProfile(
            kind=ProjectKind.PYTHON,
            root=root,
            name=root.name,
            language="Python",
            engine=framework,
            version_hint=None,
            source_dirs=src_dirs,
        )

    # ── React / JS ───────────────────────────────────────────
    if _is_react(root, top_files):
        src_dirs = [root / "src"] if (root / "src").exists() else [root]
        return ProjectProfile(
            kind=ProjectKind.REACT,
            root=root,
            name=root.name,
            language="TypeScript/JavaScript",
            engine="React",
            version_hint=None,
            source_dirs=src_dirs,
        )

    # ── Unknown ──────────────────────────────────────────────
    return ProjectProfile(
        kind=ProjectKind.UNKNOWN,
        root=root,
        name=root.name,
        language="unknown",
        engine=None,
        version_hint=None,
        source_dirs=[root],
    )


# ── Detection Helpers ─────────────────────────────────────────────────

def _is_unity(root: Path, top_dirs: set, top_files: set) -> bool:
    required_dirs = {"Assets", "ProjectSettings"}
    if required_dirs.issubset(top_dirs):
        return True
    # Check for Assembly-CSharp.csproj
    if any(f == "Assembly-CSharp.csproj" for f in top_files):
        return True
    return False

def _is_unreal(root: Path, top_files: set, all_exts: set) -> bool:
    if any(f.endswith(".uproject") for f in top_files):
        return True
    if ".uproject" in all_exts:
        return True
    if (root / "Source").exists() and ".cpp" in all_exts:
        # Check for UCLASS macro (sampled check)
        for cpp in list((root / "Source").rglob("*.h"))[:10]:
            try:
                if "UCLASS" in cpp.read_text(encoding="utf-8", errors="replace"):
                    return True
            except:
                pass
    return False

def _is_dotnet(root: Path, top_files: set, all_exts: set) -> bool:
    if any(f.endswith(".csproj") or f.endswith(".sln") for f in top_files):
        return True
    if ".csproj" in all_exts or ".sln" in all_exts:
        return True
    return False

def _is_cpp(root: Path, top_files: set, all_exts: set) -> bool:
    cpp_exts = {".cpp", ".h", ".hpp", ".cc", ".cxx"}
    if not (cpp_exts & all_exts):
        return False
    top_dirs = {d.name for d in root.iterdir() if d.is_dir()} if root.is_dir() else set()
    # Cocos2d-x: Classes/ + (cocos2d/ or proj.* directory)
    if (root / "Classes").exists() and (
        "cocos2d" in top_dirs
        or any(d.startswith("proj.") for d in top_dirs)
    ):
        return True
    # Generic C++
    cmake    = "CMakeLists.txt" in top_files
    vcxproj  = any(f.endswith(".vcxproj") for f in top_files)
    makefile = "Makefile" in top_files or "GNUmakefile" in top_files
    return cmake or vcxproj or makefile

def _is_python(root: Path, top_files: set) -> bool:
    python_markers = {
        "requirements.txt", "setup.py", "setup.cfg",
        "pyproject.toml", "Pipfile", "poetry.lock"
    }
    return bool(python_markers & top_files)

def _is_react(root: Path, top_files: set) -> bool:
    if "package.json" not in top_files:
        return False
    try:
        pkg = (root / "package.json").read_text(encoding="utf-8")
        return '"react"' in pkg
    except:
        return False


def _collect_extensions(root: Path, max_depth: int = 2) -> set:
    """Collect file extensions up to max_depth using scandir (much faster than rglob)."""
    import os as _os
    exts = set()
    def _walk(path: Path, depth: int):
        if depth > max_depth:
            return
        try:
            with _os.scandir(path) as it:
                for entry in it:
                    if entry.is_file(follow_symlinks=False):
                        _, ext = _os.path.splitext(entry.name)
                        if ext:
                            exts.add(ext.lower())
                    elif entry.is_dir(follow_symlinks=False):
                        _walk(Path(entry.path), depth + 1)
        except (PermissionError, OSError):
            pass
    _walk(root, 1)
    return exts


def _read_unity_version(root: Path) -> str | None:
    version_file = root / "ProjectSettings" / "ProjectVersion.txt"
    try:
        text = version_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("m_EditorVersion:"):
                return line.split(":", 1)[1].strip()
    except:
        pass
    return None


def _read_unreal_version(root: Path) -> str | None:
    # Try finding version hints in Saved/Logs or uproject file
    try:
        uproject = next(root.glob("*.uproject"), None)
        if uproject:
            import json
            data = json.loads(uproject.read_text(encoding="utf-8"))
            return data.get("EngineAssociation")
    except:
        pass
    return None


def _read_dotnet_target(csproj: Path) -> str | None:
    try:
        text = csproj.read_text(encoding="utf-8")
        import re
        m = re.search(r'<TargetFramework>(.*?)</TargetFramework>', text)
        if m: return m.group(1)
    except:
        pass
    return None

def _is_axmol(root: Path, top_files: set, top_dirs: set) -> bool:
    """Detect Axmol engine project: ax/ directory or CMakeLists.txt containing 'axmol'."""
    if "ax" in top_dirs:
        return True
    if "CMakeLists.txt" in top_files:
        try:
            text = (root / "CMakeLists.txt").read_text(encoding="utf-8", errors="replace")
            if "axmol" in text.lower():
                return True
        except Exception:
            pass
    return False

def _read_axmol_version(root: Path) -> str | None:
    """Try to read Axmol engine version from CMakeLists.txt."""
    cmake = root / "CMakeLists.txt"
    import re as _re
    try:
        text = cmake.read_text(encoding="utf-8", errors="replace")
        m = _re.search(r'set\s*\(\s*AX_VERSION\s+["\']?(\d+\.\d+[\.\d]*)', text, _re.IGNORECASE)
        if m:
            return m.group(1)
        m = _re.search(r'axmol[_\-\s]*version[^\d]*(\d+\.\d+[\.\d]*)', text, _re.IGNORECASE)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None

def _read_cocos_version(root: Path) -> str | None:
    """Reads Cocos2d-x version."""
    candidates = [
        root / "cocos2d" / "cocos" / "base" / "ccConfig.h",
        root / "cocos2d" / "cocos" / "cocos2d.h",
    ]
    import re as _re
    ver_pat = _re.compile(r'COCOS2D[_-]VERSION[^\d]*(\d+\.\d+[\.\d]*)')
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            m = ver_pat.search(text)
            if m: return m.group(1)
        except Exception:
            pass
    return None

def _detect_python_framework(root: Path, top_files: set) -> str:
    try:
        if "requirements.txt" in top_files:
            reqs = (root / "requirements.txt").read_text(encoding="utf-8").lower()
            if "django" in reqs:   return "Django"
            if "fastapi" in reqs:  return "FastAPI"
            if "flask" in reqs:    return "Flask"
            if "streamlit" in reqs: return "Streamlit"
    except:
        pass
    return "Python"

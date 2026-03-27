"""
gdep.uasset_cache
Shared mtime-fingerprint cache for uasset binary scan results.

두 종류의 fingerprint를 제공합니다:
  fingerprint_content(roots)  — .uasset/.umap mtime+size  (BP/BT/ST/ABP/GAS asset용)
  fingerprint_source(roots)   — .h/.cpp mtime+size         (C++ 소스 스캔용)
  fingerprint_combined(c, s)  — 두 결과를 합산             (analyze_gas처럼 둘 다 쓰는 경우)

캐시 무효화 기준:
  - uasset 전용 분석 (build_bp_map / analyze_abp / BT / ST):
      Content 파일 변경 시 자동 무효화 (fingerprint_content)
  - C++ + uasset 혼합 분석 (analyze_gas):
      Content 또는 Source 어느 쪽이든 변경되면 무효화 (fingerprint_combined)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

_CACHE_DIR_NAME = ".gdep/cache"
_IGNORE_DIRS    = frozenset({"__ExternalActors__", "__ExternalObjects__",
                              "Collections", "Developers"})


def _cache_dir(project_path: str) -> Path:
    """Return .gdep_cache directory next to the project root."""
    p = Path(project_path).resolve()
    # Walk up to find project root (contains Content or Source)
    for candidate in [p] + list(p.parents):
        if (candidate / "Content").is_dir() or (candidate / "Source").is_dir():
            return candidate / _CACHE_DIR_NAME
    return p / _CACHE_DIR_NAME


def _safe_key(cache_key: str) -> str:
    """Sanitize cache key for use as a filename."""
    return re.sub(r'[^\w\-]', '_', cache_key)[:80]


def load_cache(project_path: str, cache_key: str) -> dict | None:
    """Load cached JSON object. Returns None if missing, corrupt, or version mismatch."""
    from . import __version__
    path = _cache_dir(project_path) / f"{_safe_key(cache_key)}.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("_gdep_ver", "") != __version__:
            return None  # gdep 버전 불일치 → 무효화
        return data
    except Exception:
        return None


def save_cache(project_path: str, cache_key: str, data: dict) -> None:
    """Persist data dict as JSON cache with gdep version. Silently ignores write errors."""
    from . import __version__
    data["_gdep_ver"] = __version__
    d = _cache_dir(project_path)
    try:
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{_safe_key(cache_key)}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
    except Exception:
        pass


def fingerprint_content(content_roots: list[Path]) -> str:
    """
    .uasset / .umap 파일의 mtime+size MD5.
    BP 매핑 / BT / ST / ABP 캐시에 사용.
    Content 폴더가 바뀔 때만 무효화됨.
    """
    h = hashlib.md5()
    for root in sorted(content_roots):
        if not root.exists():
            continue
        stack = [str(root)]
        while stack:
            cur = stack.pop()
            try:
                with os.scandir(cur) as it:
                    for entry in sorted(it, key=lambda e: e.name):
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name not in _IGNORE_DIRS:
                                stack.append(entry.path)
                        elif entry.name.endswith((".uasset", ".umap")):
                            st = entry.stat()
                            h.update(f"{entry.path}:{st.st_mtime}:{st.st_size}\n"
                                     .encode("utf-8", "ignore"))
            except PermissionError:
                continue
    return h.hexdigest()


def fingerprint_source(source_roots: list[Path]) -> str:
    """
    .h / .cpp 파일의 mtime+size MD5.
    C++ 소스를 직접 파싱하는 analyze_gas 캐시에 사용.
    git pull / 코드 수정으로 .h 파일이 바뀌면 무효화됨.
    """
    h = hashlib.md5()
    for root in sorted(source_roots):
        if not root.exists():
            continue
        stack = [str(root)]
        while stack:
            cur = stack.pop()
            try:
                with os.scandir(cur) as it:
                    for entry in sorted(it, key=lambda e: e.name):
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.name.endswith((".h", ".cpp")):
                            st = entry.stat()
                            h.update(f"{entry.path}:{st.st_mtime}:{st.st_size}\n"
                                     .encode("utf-8", "ignore"))
            except PermissionError:
                continue
    return h.hexdigest()


def fingerprint_combined(content_roots: list[Path],
                         source_roots: list[Path]) -> str:
    """
    Content(.uasset) + Source(.h/.cpp) 를 모두 포함한 합산 fingerprint.
    analyze_gas처럼 C++ 소스와 uasset을 동시에 분석하는 경우에 사용.
    어느 쪽이 변경돼도 캐시를 무효화함.
    """
    fp_c = fingerprint_content(content_roots)
    fp_s = fingerprint_source(source_roots)
    return hashlib.md5(f"{fp_c}:{fp_s}".encode()).hexdigest()

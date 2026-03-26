"""
gdep.confidence
공통 신뢰도 레이어 — 분석 방법·커버리지·신뢰도를 MCP 응답 상단에 투명하게 표시한다.

핵심 원칙: 한계를 숨기는 도구보다, 한계를 정직하게 표시하는 도구가 더 빠르게 표준이 된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ConfidenceTier(str, Enum):
    HIGH   = "high"    # C++ / Roslyn 소스 직접 파싱 — 확정적
    MEDIUM = "medium"  # Binary NativeParentClass 필드 + cross-reference — 신뢰할 수 있음
    LOW    = "low"     # 넓은 바이너리 regex / 파일명 휴리스틱
    NONE   = "none"    # LFS 스텁, 읽기 불가 등 — 파싱 불가


@dataclass
class AnalysisMetadata:
    """분석 방법·커버리지·신뢰도를 담는 메타데이터."""
    source_method:  str            = ""       # e.g. "cpp_source_regex + binary_pattern_match"
    confidence:     ConfidenceTier = ConfidenceTier.NONE
    scanned:        int            = 0        # 발견된 전체 에셋 수
    parsed:         int            = 0        # 실제 파싱 성공한 에셋 수
    skipped_lfs:    int            = 0        # Git LFS 스텁으로 건너뜀
    skipped_error:  int            = 0        # 읽기 오류로 건너뜀
    ue_version:     str            = ""       # .uproject EngineAssociation 값

    @property
    def coverage_pct(self) -> float:
        return round(100.0 * self.parsed / self.scanned, 1) if self.scanned else 0.0

    def to_header(self) -> str:
        """MCP 응답 상단에 삽입할 신뢰도 헤더 블록."""
        lines = [
            f"> Analysis method: {self.source_method}",
            f"> Confidence: **{self.confidence.value.upper()}**",
            f"> Coverage: {self.parsed}/{self.scanned} assets parsed ({self.coverage_pct}%)",
        ]
        if self.skipped_lfs:
            lines.append(f"> ⚠ Skipped (Git LFS stubs): {self.skipped_lfs}"
                         f"  — binary content unavailable, results may be incomplete")
        if self.skipped_error:
            lines.append(f"> Skipped (read errors): {self.skipped_error}")
        if self.ue_version:
            tier = _ue_version_tier(self.ue_version)
            if tier == "validated":
                lines.append(f"> UE version: {self.ue_version} (validated)")
            elif tier == "experimental":
                _vrange = f"{_UE5_VALIDATED[0]}–{_UE5_VALIDATED[-1]}"
                lines.append(
                    f"> ⚠ UE {self.ue_version} detected — binary format may differ from "
                    f"validated range ({_vrange}). Verify structural decisions against C++ source."
                )
            elif tier == "unsupported":
                lines.append(
                    f"> ⚠ UE {self.ue_version} detected — UE4 is not fully supported. "
                    f"Results may be inaccurate."
                )
            else:
                lines.append(f"> UE version: {self.ue_version}")
        return "\n".join(lines)


# ── UE 버전 호환성 ────────────────────────────────────────────

_UE5_VALIDATED    = ("5.0", "5.1", "5.2", "5.3", "5.4", "5.5", "5.6")
_UE5_EXPERIMENTAL = ("5.7", "5.8", "5.9")


def _ue_version_tier(version: str) -> str:
    if any(version.startswith(v) for v in _UE5_VALIDATED):
        return "validated"
    if any(version.startswith(v) for v in _UE5_EXPERIMENTAL):
        return "experimental"
    if version.startswith("4."):
        return "unsupported"
    return "unknown"

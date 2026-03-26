/**
 * ConfidenceBadge — gdep 분석 신뢰도 등급 표시 컴포넌트
 *
 * CLI/MCP 도구들이 분석 결과 마지막 줄에 아래 형식으로 신뢰도를 첨부함:
 *   [Confidence: HIGH | source-level control flow]
 *   [Confidence: MEDIUM | binary .uasset pattern match]
 *   [Confidence: LOW | heuristic]
 *
 * extractConfidence(text)로 텍스트에서 등급과 메모를 파싱할 수 있음.
 */
import type { ReactNode } from 'react'

export type ConfidenceTier = 'HIGH' | 'MEDIUM' | 'LOW'

const TIER_STYLE: Record<ConfidenceTier, string> = {
  HIGH:   'bg-emerald-900 border-emerald-700 text-emerald-300',
  MEDIUM: 'bg-yellow-900  border-yellow-700  text-yellow-300',
  LOW:    'bg-red-900     border-red-700     text-red-300',
}

const TIER_DOT: Record<ConfidenceTier, ReactNode> = {
  HIGH:   <span className="text-emerald-400">●</span>,
  MEDIUM: <span className="text-yellow-400">●</span>,
  LOW:    <span className="text-red-400">●</span>,
}

/** 텍스트 결과에서 신뢰도 정보를 파싱
 *
 * 지원 포맷:
 *   1) confidence_footer():  "> Confidence: **HIGH** (source-level control flow)"
 *   2) AnalysisMetadata:     "> Confidence: **HIGH**"
 *   3) 레거시(미사용):        "[Confidence: HIGH | note]"
 */
export function extractConfidence(text: string): { tier: ConfidenceTier; note: string } | null {
  // 포맷 1/2: "> Confidence: **HIGH** (...)"
  const m = text.match(/>\s*Confidence:\s*\*\*(HIGH|MEDIUM|LOW)\*\*\s*(?:\(([^)\n]*)\))?/i)
  if (m) {
    return {
      tier: m[1].toUpperCase() as ConfidenceTier,
      note: m[2]?.trim() ?? '',
    }
  }
  // 포맷 3 (레거시): "[Confidence: HIGH | note]"
  const m2 = text.match(/\[Confidence:\s*(HIGH|MEDIUM|LOW)\s*(?:\|\s*([^\]]*))?\]/i)
  if (m2) {
    return {
      tier: m2[1].toUpperCase() as ConfidenceTier,
      note: m2[2]?.trim() ?? '',
    }
  }
  return null
}

/** 신뢰도 표시 뱃지 */
export function ConfidenceBadge({ tier, note }: { tier: ConfidenceTier; note?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border font-medium
                  ${TIER_STYLE[tier]}`}
      title={note ? `Confidence: ${tier} — ${note}` : `Confidence: ${tier}`}>
      {TIER_DOT[tier]}
      {tier}
      {note && <span className="text-xs opacity-70 font-normal max-w-[160px] truncate">{note}</span>}
    </span>
  )
}

/** 분석 결과 텍스트에서 자동으로 신뢰도를 추출해 뱃지를 렌더링 */
export function ConfidenceFromText({ text }: { text: string }) {
  const conf = extractConfidence(text)
  if (!conf) return null
  return <ConfidenceBadge tier={conf.tier} note={conf.note} />
}

import { useState, useRef, useCallback, useEffect } from 'react'
import { useApp } from '../store'

// ── 공통 타입 ────────────────────────────────────────────────────

interface LintItem {
  rule_id:  string
  severity: string   // "Error" | "Warning"
  message:  string
  class:    string
}

// ── 메시지 타입 ──────────────────────────────────────────────────

type WatchMsg =
  | { type: 'connected';   path: string; engine: string; debounce: number; depth: number; target_class: string | null }
  | { type: 'changed';     file: string; class: string; timestamp: string }
  | { type: 'impact';      class: string; count: number; ok: boolean; output: string }
  | { type: 'test_scope';  count: number; files: string[]; ok: boolean }
  | { type: 'lint';        errors: number; warnings: number; cycles: number; first_error_rule: string; items: LintItem[]; ok: boolean }
  | { type: 'done';        elapsed: number }
  | { type: 'heartbeat' }
  | { type: 'error';       message: string }

// ── 분석 결과 묶음 ───────────────────────────────────────────────

interface AnalysisResult {
  id:        number
  file:      string
  className: string
  timestamp: string
  impact?:   { count: number; ok: boolean; output: string }
  testScope?: { count: number; files: string[]; ok: boolean }
  lint?:     { errors: number; warnings: number; cycles: number; first_error_rule: string; items: LintItem[]; ok: boolean }
  elapsed?:  number
  done:      boolean
}

// ── 유틸 ─────────────────────────────────────────────────────────

const WS_URL = 'ws://localhost:8000/api/watch'

function severity(r: AnalysisResult): 'error' | 'warning' | 'ok' | 'running' {
  if (!r.done) return 'running'
  if (r.lint && (r.lint.errors > 0 || r.lint.cycles > 0)) return 'error'
  if (r.lint && r.lint.warnings > 0) return 'warning'
  return 'ok'
}

const SEV_COLOR = {
  error:   'border-red-600 bg-red-950/30',
  warning: 'border-yellow-600 bg-yellow-950/20',
  ok:      'border-green-700 bg-green-950/20',
  running: 'border-blue-700 bg-blue-950/20',
}
const SEV_BADGE = {
  error:   'bg-red-700 text-red-100',
  warning: 'bg-yellow-700 text-yellow-100',
  ok:      'bg-green-700 text-green-100',
  running: 'bg-blue-700 text-blue-100',
}
// SEV_LABEL is resolved dynamically via t() in the render to support i18n

// ── 컴포넌트 ─────────────────────────────────────────────────────

export default function WatchPanel() {
  const { scriptsPath, t } = useApp()

  // 설정
  const [watchPath,    setWatchPath]    = useState(scriptsPath)
  const [targetClass,  setTargetClass]  = useState('')
  const [depth,        setDepth]        = useState(3)
  const [debounce,     setDebounce]     = useState(1.0)

  // 상태
  const [watching,     setWatching]     = useState(false)
  const [engine,       setEngine]       = useState(''); void engine
  const [statusMsg,    setStatusMsg]    = useState('')
  const [results,      setResults]      = useState<AnalysisResult[]>([])
  const [expanded,     setExpanded]     = useState<Set<number>>(new Set())

  const wsRef      = useRef<WebSocket | null>(null)
  const pendingRef = useRef<AnalysisResult | null>(null)
  const idRef      = useRef(0)
  const listRef    = useRef<HTMLDivElement>(null)

  // scriptsPath 변경 시 watchPath 동기화 (입력 안 건드린 경우에만)
  useEffect(() => {
    if (!watching) setWatchPath(scriptsPath)
  }, [scriptsPath, watching])

  // 새 결과 추가 시 스크롤
  useEffect(() => {
    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }, [results.length])

  const handleMsg = useCallback((raw: string) => {
    let msg: WatchMsg
    try { msg = JSON.parse(raw) }
    catch { return }

    if (msg.type === 'heartbeat') return

    if (msg.type === 'error') {
      setStatusMsg(`Error: ${msg.message}`)
      return
    }

    if (msg.type === 'connected') {
      setEngine(msg.engine)
      setStatusMsg(`Watching — ${msg.engine}  (depth=${msg.depth}, debounce=${msg.debounce}s)`)
      return
    }

    if (msg.type === 'changed') {
      const r: AnalysisResult = {
        id:        ++idRef.current,
        file:      msg.file,
        className: msg.class,
        timestamp: msg.timestamp,
        done:      false,
      }
      pendingRef.current = r
      setResults(prev => [r, ...prev])
      return
    }

    // impact / test_scope / lint / done → 현재 pending에 합산
    setResults(prev => {
      if (!prev.length) return prev
      const [head, ...tail] = prev
      let updated = { ...head }

      if (msg.type === 'impact')     updated.impact    = { count: msg.count, ok: msg.ok, output: msg.output }
      if (msg.type === 'test_scope') updated.testScope = { count: msg.count, files: msg.files, ok: msg.ok }
      if (msg.type === 'lint')       updated.lint      = { errors: msg.errors, warnings: msg.warnings, cycles: msg.cycles, first_error_rule: msg.first_error_rule, items: msg.items ?? [], ok: msg.ok }
      if (msg.type === 'done')       { updated.elapsed = msg.elapsed; updated.done = true }

      return [updated, ...tail]
    })
  }, [])

  const startWatch = useCallback(() => {
    if (wsRef.current) wsRef.current.close()

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify({
        action:       'start',
        path:         watchPath,
        target_class: targetClass || null,
        depth,
        debounce,
      }))
      setWatching(true)
      setStatusMsg('Connecting…')
    }

    ws.onmessage = (e) => handleMsg(e.data)

    ws.onclose = () => {
      setWatching(false)
      setStatusMsg(prev => prev.startsWith('Error') ? prev : 'Watch stopped')
      wsRef.current = null
    }

    ws.onerror = () => {
      setStatusMsg('WebSocket connection failed — check that the backend server is running.')
    }
  }, [watchPath, targetClass, depth, debounce, handleMsg])

  const stopWatch = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ action: 'stop' }))
      wsRef.current.close()
    }
  }, [])

  const toggleExpand = (id: number) =>
    setExpanded(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })

  // ── 렌더 ───────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full p-4 gap-4 overflow-hidden">

      {/* 설정 패널 */}
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 shrink-0">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">{t('watch_title')}</h2>

        <div className="grid grid-cols-[1fr_auto] gap-2 mb-3">
          <input
            className="input text-sm"
            placeholder={t('path_placeholder')}
            value={watchPath}
            onChange={e => setWatchPath(e.target.value)}
            disabled={watching}
          />
          <button
            onClick={watching ? stopWatch : startWatch}
            disabled={!watchPath}
            className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
              watching
                ? 'bg-red-700 hover:bg-red-600 text-white'
                : 'bg-blue-700 hover:bg-blue-600 text-white disabled:opacity-40'
            }`}
          >
            {watching ? t('stop') : t('start_watch')}
          </button>
        </div>

        <div className="flex gap-3 flex-wrap">
          <label className="flex items-center gap-1.5 text-xs text-gray-400">
            {t('class_filter')}
            <input
              className="input text-xs w-36"
              placeholder={t('class_filter_all')}
              value={targetClass}
              onChange={e => setTargetClass(e.target.value)}
              disabled={watching}
            />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-gray-400">
            depth
            <input
              type="number" min={1} max={8}
              className="input text-xs w-14 text-center"
              value={depth}
              onChange={e => setDepth(Number(e.target.value))}
              disabled={watching}
            />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-gray-400">
            debounce(s)
            <input
              type="number" min={0.1} max={10} step={0.1}
              className="input text-xs w-16 text-center"
              value={debounce}
              onChange={e => setDebounce(Number(e.target.value))}
              disabled={watching}
            />
          </label>
        </div>

        {/* 상태 표시 */}
        {statusMsg && (
          <div className={`mt-2 text-xs px-2 py-1 rounded flex items-center gap-1.5 ${
            watching ? 'text-blue-300 bg-blue-950/40' :
            statusMsg.startsWith('오류') ? 'text-red-300 bg-red-950/30' : 'text-gray-400'
          }`}>
            {watching && <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse inline-block" />}
            {statusMsg}
          </div>
        )}
      </div>

      {/* 결과 목록 */}
      <div ref={listRef} className="flex-1 overflow-y-auto flex flex-col gap-3">
        {results.length === 0 && (
          <div className="text-center text-gray-600 text-sm mt-12">
            {watching ? t('watch_empty_watching') : t('watch_empty_idle')}
          </div>
        )}

        {results.map(r => {
          const sev = severity(r)
          const isOpen = expanded.has(r.id)

          return (
            <div key={r.id} className={`border rounded-lg overflow-hidden ${SEV_COLOR[sev]}`}>
              {/* 헤더 */}
              <button
                className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-white/5 transition-colors"
                onClick={() => toggleExpand(r.id)}
              >
                <span className={`text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ${SEV_BADGE[sev]}`}>
                  {t(({ error:'sev_error', warning:'sev_warning', ok:'sev_ok', running:'sev_running' } as const)[sev])}
                </span>
                <span className="font-mono text-sm text-blue-300 font-semibold shrink-0">{r.className}</span>
                <span className="text-xs text-gray-500 shrink-0">{r.file}</span>
                <span className="flex-1" />
                {r.done && (
                  <span className="text-xs text-gray-500 shrink-0">{r.elapsed}s</span>
                )}
                <span className="text-xs text-gray-600 shrink-0">{r.timestamp}</span>
                <span className="text-gray-600 text-xs shrink-0">{isOpen ? '▲' : '▼'}</span>
              </button>

              {/* 요약 행 */}
              {(r.impact || r.testScope || r.lint) && (
                <div className="px-3 pb-1 flex gap-4 text-xs text-gray-400">
                  {r.impact && (
                    <span>{t('impact_count')} <b className="text-white">{r.impact.count}</b></span>
                  )}
                  {r.testScope && (
                    <span>{t('test_count')} <b className="text-white">{r.testScope.count}</b></span>
                  )}
                  {r.lint && r.lint.errors > 0 && (
                    <span className="text-red-400">× {r.lint.errors} {t('error_unit')}{r.lint.first_error_rule ? ` [${r.lint.first_error_rule}]` : ''}</span>
                  )}
                  {r.lint && r.lint.warnings > 0 && (
                    <span className="text-yellow-400">! {r.lint.warnings} {t('warning_unit')}</span>
                  )}
                  {r.lint && r.lint.cycles > 0 && (
                    <span className="text-orange-400">⚠ {t('cycle_unit')} {r.lint.cycles}</span>
                  )}
                  {r.lint && r.lint.errors === 0 && r.lint.warnings === 0 && r.lint.cycles === 0 && (
                    <span className="text-green-400">{t('lint_ok_badge')}</span>
                  )}
                </div>
              )}

              {/* 상세 (펼쳐진 경우) */}
              {isOpen && (
                <div className="border-t border-gray-700 px-3 py-2 flex flex-col gap-3">

                  {/* impact 출력 */}
                  {r.impact && r.impact.output && (
                    <div>
                      <div className="text-xs text-gray-500 mb-1 font-semibold">{t('impact_section')}</div>
                      <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono bg-gray-900 rounded p-2 max-h-40 overflow-y-auto">
                        {r.impact.output}
                      </pre>
                    </div>
                  )}

                  {/* test files */}
                  {r.testScope && r.testScope.files.length > 0 && (
                    <div>
                      <div className="text-xs text-gray-500 mb-1 font-semibold">{t('test_section')}</div>
                      <ul className="text-xs text-blue-300 font-mono space-y-0.5">
                        {r.testScope.files.map((f, i) => (
                          <li key={i} className="truncate">• {f}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {r.testScope && r.testScope.count === 0 && (
                    <div className="text-xs text-gray-500">{t('no_test')}</div>
                  )}

                  {/* lint 상세 */}
                  {r.lint && r.lint.items && r.lint.items.length > 0 && (
                    <div>
                      <div className="text-xs text-gray-500 mb-1 font-semibold">{t('lint_section')}</div>
                      <ul className="flex flex-col gap-1">
                        {r.lint.items.map((item, i) => (
                          <li key={i} className={`text-xs font-mono rounded px-2 py-1 flex gap-2 items-start ${
                            item.severity === 'Error'
                              ? 'bg-red-950/40 text-red-300'
                              : 'bg-yellow-950/30 text-yellow-300'
                          }`}>
                            <span className="shrink-0 font-semibold">
                              {item.severity === 'Error' ? '×' : '!'} [{item.rule_id}]
                            </span>
                            <span className="text-gray-300 break-all">
                              {item.class ? <span className="text-blue-300">{item.class}: </span> : null}
                              {item.message}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {r.lint && r.lint.errors === 0 && r.lint.warnings === 0 && r.lint.cycles === 0 && (
                    <div className="text-xs text-green-400">{t('lint_ok_detail')}</div>
                  )}

                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* 푸터: 누적 통계 */}
      {results.length > 0 && (
        <div className="shrink-0 text-xs text-gray-600 flex gap-4 justify-end">
          <span>{t('total_detected')}: {results.length}{t('times')}</span>
          <span className="text-red-500">{t('sev_error')}: {results.filter(r => r.done && r.lint && r.lint.errors > 0).length}</span>
          <span className="text-yellow-500">{t('sev_warning')}: {results.filter(r => r.done && r.lint && r.lint.warnings > 0).length}</span>
          <button
            className="text-gray-600 hover:text-gray-400 transition-colors"
            onClick={() => setResults([])}
          >
            {t('clear_history')}
          </button>
        </div>
      )}
    </div>
  )
}

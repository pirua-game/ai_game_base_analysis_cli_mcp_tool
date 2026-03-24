import { useState, useRef, useEffect } from 'react'
import { Send, Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import { useApp } from '../store'
import { runAgent, resetAgent, type AgentEvent } from '../api/client'

const SESSION_ID = `gdep_${Date.now()}`

const PRESETS = [
  { label: '🗺️ 온보딩',      q: '이 프로젝트의 핵심 클래스와 전체 구조를 신규 팀원에게 설명해줘' },
  { label: '🔍 순환 참조',    q: '순환 참조 원인을 분석하고 해결 방안을 제시해줘' },
  { label: '⚡ God Object',   q: 'God Object 패턴이 있는 클래스를 찾고 리팩토링 방향을 제시해줘' },
  { label: '🧹 단일 책임',    q: '단일 책임 원칙을 위반하는 클래스를 찾고 개선 방안을 제시해줘' },
  { label: '⚡ GAS 분석',     q: 'GAS 시스템의 어빌리티, 이펙트, 어트리뷰트셋 구조를 설명해줘' },
  { label: '🎭 애니메이션',   q: '이 프로젝트의 애니메이션 구조(ABP 상태, 몽타주, GAS 노티파이)를 분석해줘' },
  { label: '🤖 AI 행동',      q: 'BehaviorTree 또는 StateTree 구조를 분석하고 AI 행동 패턴을 설명해줘' },
]

interface Message {
  role:    'user' | 'assistant' | 'tool_log'
  content: string
  tools?:  { name: string; args: Record<string, unknown>; result: string }[]
}

const TOOL_ICONS: Record<string, string> = {
  scan: '🔍', describe: '📋', flow: '🔀',
  graph: '🕸️', read_source: '📄', find_prefab_refs: '📦',
}

export default function AgentChat() {
  const { scriptsPath, llmConfig, t } = useApp()
  const [messages,  setMessages]  = useState<Message[]>([])
  const [input,     setInput]     = useState('')
  const [running,   setRunning]   = useState(false)
  const [maxCalls,  setMaxCalls]  = useState(4)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function submit(q?: string) {
    const question = (q ?? input).trim()
    if (!question || running || !scriptsPath) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: question }])
    setRunning(true)

    let toolLog: Message['tools'] = []
    let currentTools: typeof toolLog = []

    runAgent(
      SESSION_ID,
      scriptsPath,
      question,
      llmConfig,
      maxCalls,
      (event: AgentEvent) => {
        if (event.type === 'tool_call') {
          currentTools = [...(toolLog ?? []), {
            name:   event.tool ?? '',
            args:   event.args ?? {},
            result: '',
          }]
          toolLog = currentTools
        } else if (event.type === 'tool_result') {
          // 마지막 도구에 결과 추가
          if (currentTools.length > 0) {
            currentTools[currentTools.length - 1].result = event.result ?? ''
          }
        } else if (event.type === 'answer') {
          const tools = [...(toolLog ?? [])]
          setMessages(prev => [...prev, {
            role:    'assistant',
            content: event.content ?? '',
            tools:   tools.length > 0 ? tools : undefined,
          }])
          toolLog    = []
          currentTools = []
        } else if (event.type === 'error') {
          setMessages(prev => [...prev, {
            role:    'assistant',
            content: `${t('error_msg')}: ${event.message}`,
          }])
        }
      },
      () => setRunning(false),
    )
  }

  async function clear() {
    await resetAgent(SESSION_ID)
    setMessages([])
  }

  if (!scriptsPath) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        {t('agent_no_path')}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">

      {/* 헤더 */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-800 shrink-0">
        <span className="text-sm text-gray-400">
          {t('agent_description')}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <label className="text-xs text-gray-500">{t('max_calls')}</label>
          <select
            className="input text-xs w-16 py-1"
            value={maxCalls}
            onChange={e => setMaxCalls(Number(e.target.value))}
          >
            {[2,3,4,5,6].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          <button onClick={clear} className="btn-ghost flex items-center gap-1 text-xs">
            <Trash2 size={13} /> {t('reset')}
          </button>
        </div>
      </div>

      {/* 프리셋 */}
      {messages.length === 0 && (
        <div className="px-4 py-3 border-b border-gray-800 flex flex-wrap gap-2 shrink-0">
          {PRESETS.map(p => (
            <button
              key={p.label}
              onClick={() => submit(p.q)}
              className="btn-secondary text-xs"
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      {/* 메시지 목록 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i}>
            {msg.role === 'user' ? (
              <div className="flex justify-end">
                <div className="max-w-lg bg-emerald-900 border border-emerald-800
                                text-emerald-100 rounded-lg px-4 py-2 text-sm">
                  {msg.content}
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {/* 도구 호출 로그 */}
                {msg.tools && msg.tools.length > 0 && (
                  <ToolLog tools={msg.tools} />
                )}
                {/* 답변 */}
                <div className="card p-4 text-sm text-gray-200 leading-relaxed
                                whitespace-pre-wrap max-w-3xl">
                  {msg.content}
                </div>
              </div>
            )}
          </div>
        ))}

        {running && (
          <div className="flex items-center gap-2 text-gray-500 text-sm">
            <div className="flex gap-1">
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            {t('analyzing_dots')}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 입력 */}
      <div className="px-4 py-3 border-t border-gray-800 shrink-0">
        <div className="flex gap-2">
          <textarea
            className="input flex-1 resize-none text-sm"
            rows={2}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submit()
              }
            }}
            placeholder={messages.length > 0
              ? t('followup_placeholder')
              : t('first_placeholder')}
            disabled={running}
          />
          <button
            onClick={() => submit()}
            disabled={!input.trim() || running}
            className="btn-primary px-4 flex items-center gap-1 self-end disabled:opacity-50"
          >
            <Send size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}

function ToolLog({ tools }: { tools: NonNullable<Message['tools']> }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="card border-gray-700 max-w-3xl">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 w-full px-3 py-2 text-xs text-gray-400 hover:text-gray-200"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {/* ToolLog doesn't have t() — use static bilingual label */}
        🔧 Tool calls {tools.length}
      </button>
      {open && (
        <div className="border-t border-gray-800 divide-y divide-gray-800">
          {tools.map((t, i) => (
            <div key={i} className="px-3 py-2">
              <p className="text-xs font-mono text-yellow-400">
                {TOOL_ICONS[t.name] ?? '🔧'} {t.name}(
                {Object.entries(t.args).map(([k,v]) => `${k}=${v}`).join(', ')}
                )
              </p>
              {t.result && (
                <pre className="text-xs text-gray-400 mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap">
                  {t.result.slice(0, 400)}{t.result.length > 400 ? '...' : ''}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

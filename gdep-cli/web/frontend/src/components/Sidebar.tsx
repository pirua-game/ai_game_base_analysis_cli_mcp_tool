import { useState, useEffect, useRef, ReactNode } from 'react'
import { RefreshCw, ChevronDown, Info } from 'lucide-react'
import { useApp, type EngineProfile } from '../store'
import { projectApi, llmApi } from '../api/client'

// ── 툴팁 (fixed 포지셔닝으로 클리핑 방지) ────────────────────
function Tip({ text, children }: { text: string; children: ReactNode }) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const ref = useRef<HTMLSpanElement>(null)

  function show() {
    if (!ref.current) return
    const r = ref.current.getBoundingClientRect()
    setPos({ x: r.right + 8, y: r.top + r.height / 2 })
  }

  return (
    <span ref={ref} className="relative inline-flex items-center"
      onMouseEnter={show} onMouseLeave={() => setPos(null)}>
      {children}
      {pos && (
        <div
          className="fixed z-[9999] w-56 bg-gray-700 text-gray-100 text-xs
                     rounded px-2.5 py-1.5 shadow-xl leading-snug pointer-events-none"
          style={{ left: pos.x, top: pos.y, transform: 'translateY(-50%)' }}
        >
          {text}
        </div>
      )}
    </span>
  )
}

function Label({ children, tip }: { children: ReactNode; tip: string }) {
  return (
    <div className="flex items-center gap-1 mb-1.5">
      <span className="text-xs text-gray-400 uppercase tracking-wide">{children}</span>
      <Tip text={tip}>
        <Info size={11} className="text-gray-600 hover:text-gray-400 cursor-help" />
      </Tip>
    </div>
  )
}

const RECENT_KEY = 'gdep_recent_paths'
const loadRecent = (): string[] => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]') } catch { return [] } }
const saveRecent = (p: string[]) => localStorage.setItem(RECENT_KEY, JSON.stringify(p.slice(0, 5)))

const KIND_BADGE: Record<string, { icon: string; color: string }> = {
  UNITY:  { icon: '🟦', color: 'text-blue-400' },
  DOTNET: { icon: '🟩', color: 'text-green-400' },
  CPP:    { icon: '🟥', color: 'text-red-400' },
  UNREAL: { icon: '🟧', color: 'text-orange-400' },
}

const ENGINE_PROFILE_VALUES: EngineProfile[] = ['auto','unity','cocos2dx','axmol','unreal','dotnet','cpp']

export default function Sidebar() {
  const {
    scriptsPath, setScriptsPath, projectInfo, setProjectInfo,
    depth, setDepth, focusClasses, setFocusClasses,
    llmConfig, setLlmConfig,
    engineProfile, setEngineProfile,
    filterEngineClasses, setFilterEngineClasses,
    customBaseClasses, setCustomBaseClasses,
    clearCache, t,
  } = useApp()

  const [inputPath,   setInputPath]   = useState(scriptsPath)
  const [recent,      setRecent]      = useState<string[]>(loadRecent)
  const [detecting,   setDetecting]   = useState(false)
  const [showRecent,  setShowRecent]  = useState(false)
  const [focusInput,  setFocusInput]  = useState(focusClasses.join(','))
  const [customInput, setCustomInput] = useState(customBaseClasses.join(','))
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [scanningMdl,  setScanningMdl] = useState(false)

  const ENGINE_PROFILES: { value: EngineProfile; label: string }[] = [
    { value: 'auto',     label: t('engine_auto') },
    { value: 'unity',    label: '🟦 Unity' },
    { value: 'cocos2dx', label: '🟧 Cocos2d-x' },
    { value: 'axmol',    label: '🪓 Axmol' },
    { value: 'unreal',   label: '🟥 Unreal Engine' },
    { value: 'dotnet',   label: '🟩 .NET' },
    { value: 'cpp',      label: t('engine_cpp_general') },
  ]

  useEffect(() => {
    if (llmConfig.provider !== 'ollama') return
    setScanningMdl(true)
    llmApi.getOllamaModels(llmConfig.base_url)
      .then(d => {
        if (d.models.length > 0) {
          setOllamaModels(d.models)
          if (!d.models.includes(llmConfig.model))
            setLlmConfig({ ...llmConfig, model: d.models[0] })
        }
      })
      .finally(() => setScanningMdl(false))
  }, [llmConfig.provider, llmConfig.base_url])

  useEffect(() => { setFocusClasses(focusInput.split(',').map(s => s.trim()).filter(Boolean)) }, [focusInput])
  useEffect(() => { setCustomBaseClasses(customInput.split(',').map(s => s.trim()).filter(Boolean)) }, [customInput])

  async function applyPath(path: string) {
    if (!path.trim()) return
    const p = path.trim()
    setInputPath(p); setScriptsPath(p); clearCache(p)
    setDetecting(true)
    try {
      const info = await projectApi.detect(p)
      setProjectInfo(info)
      if (engineProfile === 'auto') {
        let detected: EngineProfile = 'cpp'
        if (info.kind === 'UNITY')  detected = 'unity'
        else if (info.kind === 'UNREAL') detected = 'unreal'
        else if (info.kind === 'DOTNET') detected = 'dotnet'
        else if (info.engine?.startsWith('Axmol')) detected = 'axmol'
        else if (info.engine?.toLowerCase().includes('cocos')) detected = 'cocos2dx'
        setEngineProfile(detected)
      }
      const updated = [p, ...recent.filter(x => x !== p)]
      setRecent(updated); saveRecent(updated)
    } catch { setProjectInfo(null) }
    finally { setDetecting(false) }
  }

  const badge = projectInfo ? KIND_BADGE[projectInfo.kind] : null

  return (
    <aside className="w-64 shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col h-screen">
      <div className="p-4 border-b border-gray-800 shrink-0">
        <h1 className="text-lg font-bold text-emerald-400">{t('sidebar_title')}</h1>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">

        {/* Scripts 경로 */}
        <div>
          <Label tip={t('scripts_path_tip')}>
            {t('scripts_path')}
          </Label>
          <div className="flex gap-1">
            <input className="input flex-1 text-xs" value={inputPath}
              onChange={e => setInputPath(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && applyPath(inputPath)}
              placeholder={t('scripts_path_placeholder')} />
            <button className="btn-secondary px-2 shrink-0"
              onClick={() => applyPath(inputPath)}>
              <RefreshCw size={13} className={detecting ? 'animate-spin' : ''} />
            </button>
          </div>

          {recent.length > 0 && (
            <div className="mt-1">
              <button className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
                onClick={() => setShowRecent(v => !v)}>
                <ChevronDown size={12} className={showRecent ? 'rotate-180' : ''} />
                {t('recent_paths')}
              </button>
              {showRecent && (
                <div className="mt-1 space-y-0.5">
                  {recent.map(p => (
                    <button key={p}
                      className="w-full text-left text-xs text-gray-400 hover:text-gray-200
                                 hover:bg-gray-800 rounded px-2 py-1 truncate block"
                      onClick={() => { applyPath(p); setShowRecent(false) }} title={p}>
                      {p.split(/[\\/]/).slice(-2).join('/')}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {projectInfo && (
            <p className={`mt-1.5 text-xs ${badge?.color ?? 'text-gray-400'}`}>
              {badge?.icon} {projectInfo.display}
            </p>
          )}
          {scriptsPath && (
            <button className="mt-1.5 btn-ghost text-xs w-full text-center"
              onClick={() => { clearCache(scriptsPath); window.location.reload() }}>
              {t('cache_refresh')}
            </button>
          )}
        </div>

        <hr className="border-gray-800" />

        {/* 엔진 프로파일 */}
        <div>
          <Label tip={t('engine_profile_tip')}>
            {t('engine_profile')}
          </Label>
          <select className="input text-xs" value={engineProfile}
            onChange={e => setEngineProfile(e.target.value as EngineProfile)}>
            {ENGINE_PROFILE_VALUES.map(v => {
              const p = ENGINE_PROFILES.find(x => x.value === v)!
              return <option key={v} value={v}>{p.label}</option>
            })}
          </select>
          <div className="mt-2 space-y-1.5">
            <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
              <input type="checkbox" checked={filterEngineClasses}
                onChange={e => setFilterEngineClasses(e.target.checked)}
                className="accent-emerald-500" />
              {t('engine_filter')}
            </label>
            <input className="input text-xs" value={customInput}
              onChange={e => setCustomInput(e.target.value)}
              placeholder={t('engine_custom_placeholder')} />
          </div>
        </div>

        <hr className="border-gray-800" />

        {/* 분석 깊이 */}
        <div>
          <Label tip={t('analysis_depth_tip')}>
            {t('analysis_depth')}: <span className="text-white">{depth}</span>
          </Label>
          <input type="range" min={1} max={8} value={depth}
            onChange={e => setDepth(Number(e.target.value))}
            className="w-full accent-emerald-500" />
        </div>

        {/* Focus 클래스 */}
        <div>
          <Label tip={t('focus_class_tip')}>
            {t('focus_class')}
          </Label>
          <input className="input text-xs" value={focusInput}
            onChange={e => setFocusInput(e.target.value)}
            placeholder={t('focus_class_placeholder')} />
        </div>

        <hr className="border-gray-800" />

        {/* LLM 설정 */}
        <div>
          <Label tip={t('llm_settings_tip')}>
            {t('llm_settings')}
          </Label>
          <select className="input text-xs mb-1.5" value={llmConfig.provider}
            onChange={e => setLlmConfig({ ...llmConfig, provider: e.target.value })}>
            <option value="ollama">{t('ollama_local')}</option>
            <option value="openai">OpenAI</option>
            <option value="anthropic">Claude</option>
            <option value="gemini">Gemini</option>
          </select>

          {llmConfig.provider === 'ollama' ? (
            <div className="flex gap-1">
              <select className="input text-xs flex-1" value={llmConfig.model}
                onChange={e => setLlmConfig({ ...llmConfig, model: e.target.value })}
                disabled={scanningMdl}>
                {ollamaModels.length > 0
                  ? ollamaModels.map(m => <option key={m} value={m}>{m}</option>)
                  : <option value={llmConfig.model}>{scanningMdl ? t('scanning') : llmConfig.model}</option>}
              </select>
              <button className="btn-ghost px-2 shrink-0"
                onClick={() => {
                  setScanningMdl(true)
                  llmApi.getOllamaModels(llmConfig.base_url)
                    .then(d => { if (d.models.length) setOllamaModels(d.models) })
                    .finally(() => setScanningMdl(false))
                }}>
                <RefreshCw size={13} className={scanningMdl ? 'animate-spin' : ''} />
              </button>
            </div>
          ) : (
            <>
              <input className="input text-xs mb-1" value={llmConfig.model}
                onChange={e => setLlmConfig({ ...llmConfig, model: e.target.value })}
                placeholder={t('model_placeholder')} />
              <input className="input text-xs" type="password"
                value={llmConfig.api_key ?? ''}
                onChange={e => setLlmConfig({ ...llmConfig, api_key: e.target.value })}
                placeholder={t('api_key_placeholder')} />
            </>
          )}
        </div>

      </div>
    </aside>
  )
}

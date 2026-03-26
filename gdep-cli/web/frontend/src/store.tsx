import { createContext, useContext, useState, useRef, useEffect } from 'react'
import type { ReactNode } from 'react'
import type { FlowData, ProjectInfo, LLMConfig, ClassInfo, ScanResult, PrefabRef } from './api/client'
import { type Lang, type TranslationKey, translations } from './i18n'

export type EngineProfile = 'auto' | 'unity' | 'cocos2dx' | 'unreal' | 'dotnet' | 'cpp' | 'axmol'
export type { Lang }

// ── 캐시 타입 ─────────────────────────────────────────────────
interface PathCache {
  classMap?:   Record<string, ClassInfo>
  scanResult?: ScanResult
  prefabRefs?: Record<string, PrefabRef>
}

// ── localStorage 헬퍼 ─────────────────────────────────────────
function loadTheme(): 'dark' | 'light' {
  try { return (localStorage.getItem('gdep_theme') as 'dark' | 'light') ?? 'dark' } catch { return 'dark' }
}
function loadLang(): Lang {
  try { return (localStorage.getItem('gdep_lang') as Lang) ?? 'ko' } catch { return 'ko' }
}

interface AppState {
  scriptsPath:      string
  setScriptsPath:   (p: string) => void
  projectInfo:      ProjectInfo | null
  setProjectInfo:   (p: ProjectInfo | null) => void
  flowData:         FlowData | null
  setFlowData:      (f: FlowData | null) => void
  flowHistory:      FlowData[]
  setFlowHistory:   (h: FlowData[]) => void
  breadcrumb:       { cls: string; method: string }[]
  setBreadcrumb:    (b: { cls: string; method: string }[]) => void
  selectedClass:    string
  setSelectedClass: (c: string) => void
  selectedNode:     string | null
  setSelectedNode:  (n: string | null) => void
  depth:            number
  setDepth:         (d: number) => void
  focusClasses:     string[]
  setFocusClasses:  (f: string[]) => void
  llmConfig:        LLMConfig
  setLlmConfig:     (c: LLMConfig) => void
  engineProfile:    EngineProfile
  setEngineProfile: (p: EngineProfile) => void
  filterEngineClasses:    boolean
  setFilterEngineClasses: (v: boolean) => void
  customBaseClasses:      string[]
  setCustomBaseClasses:   (v: string[]) => void
  // 캐시 접근
  getCache:    (path: string) => PathCache
  setCache:    (path: string, data: Partial<PathCache>) => void
  clearCache:  (path?: string) => void
  // 테마 / 언어
  theme:       'dark' | 'light'
  toggleTheme: () => void
  lang:        Lang
  toggleLang:  () => void
  t:           (key: TranslationKey) => string
}

const AppContext = createContext<AppState | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [scriptsPath,  setScriptsPath]  = useState('')
  const [projectInfo,  setProjectInfo]  = useState<ProjectInfo | null>(null)
  const [flowData,     setFlowData]     = useState<FlowData | null>(null)
  const [flowHistory,  setFlowHistory]  = useState<FlowData[]>([])
  const [breadcrumb,   setBreadcrumb]   = useState<{ cls: string; method: string }[]>([])
  const [selectedClass, setSelectedClass] = useState('')
  const [selectedNode,  setSelectedNode]  = useState<string | null>(null)
  const [depth,        setDepth]        = useState(3)
  const [focusClasses, setFocusClasses] = useState<string[]>([])
  const [engineProfile, setEngineProfile] = useState<EngineProfile>('auto')
  const [filterEngineClasses, setFilterEngineClasses] = useState(true)
  const [customBaseClasses,   setCustomBaseClasses]   = useState<string[]>([])
  const [llmConfig, setLlmConfig] = useState<LLMConfig>({
    provider: 'ollama', model: 'qwen2.5-coder:14b',
    base_url: 'http://localhost:11434',
  })

  const [theme, setTheme] = useState<'dark' | 'light'>(loadTheme)
  const [lang,  setLang]  = useState<Lang>(loadLang)

  // html 클래스 + localStorage 동기화
  useEffect(() => {
    const html = document.documentElement
    if (theme === 'light') { html.classList.add('light'); html.classList.remove('dark') }
    else                   { html.classList.remove('light'); html.classList.add('dark') }
    localStorage.setItem('gdep_theme', theme)
  }, [theme])

  useEffect(() => {
    localStorage.setItem('gdep_lang', lang)
  }, [lang])

  const toggleTheme = () => setTheme(v => v === 'dark' ? 'light' : 'dark')
  const toggleLang  = () => setLang(v => v === 'ko' ? 'en' : 'ko')
  const t = (key: TranslationKey): string => translations[lang][key] ?? key

  // 캐시: path → data (리렌더 유발 없이 useRef로 관리)
  const cacheRef = useRef<Record<string, PathCache>>({})

  const getCache  = (path: string) => cacheRef.current[path] ?? {}
  const setCache  = (path: string, data: Partial<PathCache>) => {
    cacheRef.current[path] = { ...cacheRef.current[path], ...data }
  }
  const clearCache = (path?: string) => {
    if (path) delete cacheRef.current[path]
    else cacheRef.current = {}
  }

  return (
    <AppContext.Provider value={{
      scriptsPath, setScriptsPath, projectInfo, setProjectInfo,
      flowData, setFlowData, flowHistory, setFlowHistory,
      breadcrumb, setBreadcrumb,
      selectedClass, setSelectedClass, selectedNode, setSelectedNode,
      depth, setDepth, focusClasses, setFocusClasses,
      llmConfig, setLlmConfig,
      engineProfile, setEngineProfile,
      filterEngineClasses, setFilterEngineClasses,
      customBaseClasses, setCustomBaseClasses,
      getCache, setCache, clearCache,
      theme, toggleTheme, lang, toggleLang, t,
    }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}

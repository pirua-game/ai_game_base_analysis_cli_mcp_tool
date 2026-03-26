import { useState, useEffect } from 'react'
import { useState as useLocalState } from 'react'
import { Search, Zap, ChevronRight, ChevronDown, ShieldAlert } from 'lucide-react'
import { useApp, type EngineProfile } from '../store'
import type { TranslationKey } from '../i18n'
import {
  classesApi, flowApi, unityApi, projectApi,
  type ClassInfo, type ClassMethod, type ClassField, type PrefabRef,
  type LintIssue, ue5Api, type BlueprintRef,
  type ExplainMethodResult, type DescribeResult,
} from '../api/client'


// ── BP 매핑 상세 카드 컴포넌트 ────────────────────────────────
function BpMappingDetail({ text }: { text: string }) {
  // "### `BP_Name` (BP_Name_C)" 로 시작하는 블록으로 분리
  const blocks: { title: string; lines: string[] }[] = []
  let current: { title: string; lines: string[] } | null = null

  for (const line of text.split('\n')) {
    if (line.startsWith('### ')) {
      if (current) blocks.push(current)
      current = { title: line.replace(/^###\s*/, '').replace(/`/g, ''), lines: [] }
    } else if (current) {
      current.lines.push(line)
    }
  }
  if (current) blocks.push(current)

  if (blocks.length === 0) {
    // 블록이 없으면 단순 텍스트 렌더링
    return (
      <div className="border-t border-gray-800 pt-2 mt-1 space-y-0.5 max-h-52 overflow-y-auto">
        {text.split('\n').map((line, i) => {
          if (line.startsWith('##')) return <p key={i} className="text-xs font-semibold text-blue-300 mt-2">{line.replace(/^#+\s*/,'')}</p>
          if (line.startsWith('-'))  return <p key={i} className="text-xs text-gray-400 pl-2">• {line.slice(1).trim()}</p>
          if (!line.trim())          return <div key={i} className="h-1" />
          return <p key={i} className="text-xs text-gray-500">{line}</p>
        })}
      </div>
    )
  }

  return (
    <div className="border-t border-gray-800 pt-2 mt-1 space-y-1">
      {blocks.map((block, idx) => (
        <BpCard key={idx} title={block.title} lines={block.lines} defaultOpen={blocks.length === 1} />
      ))}
    </div>
  )
}

function BpCard({ title, lines, defaultOpen }: { title: string; lines: string[]; defaultOpen: boolean }) {
  const [open, setOpen] = useLocalState(defaultOpen)
  const sections: { heading: string; items: string[] }[] = []
  let cur: { heading: string; items: string[] } | null = null
  for (const line of lines) {
    if (line.startsWith('  K2 overrides:') || line.startsWith('  Variables:') ||
        line.startsWith('  Tags:') || line.startsWith('  Path:') ||
        line.startsWith('  Event ')) {
      if (cur) sections.push(cur)
      const colon = line.indexOf(':')
      cur = { heading: line.slice(0, colon).trim(), items: [line.slice(colon + 1).trim()] }
    } else if (line.trim() && cur) {
      cur.items.push(line.trim())
    }
  }
  if (cur) sections.push(cur)

  return (
    <div className="rounded border border-gray-700 bg-gray-900/60 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-gray-800/50 transition-colors"
      >
        <span className="text-xs font-semibold text-blue-300 text-left truncate flex-1">{title}</span>
        <span className="text-gray-500 text-xs ml-2 shrink-0">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="px-3 pb-2 space-y-1 border-t border-gray-800">
          {sections.map((sec, i) => (
            <div key={i} className="mt-1.5">
              <p className="text-xs text-gray-500 font-medium">{sec.heading}</p>
              {sec.items.filter(Boolean).map((item, j) => (
                <p key={j} className="text-xs text-gray-300 pl-2 truncate" title={item}>• {item}</p>
              ))}
            </div>
          ))}
          {sections.length === 0 && (
            <p className="text-xs text-gray-600 mt-1">—</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── 엔진 정의 ─────────────────────────────────────────────────
const ENGINE_BASES: Record<EngineProfile, string[]> = {
  auto:     [],
  unity:    ['MonoBehaviour','ScriptableObject','Editor','EditorWindow',
             'StateMachineBehaviour','NetworkBehaviour','PlayableBehaviour'],
  cocos2dx: ['CCNode','CCLayer','CCScene','CCSprite','CCMenu','CCObject',
             'Node','Layer','Scene','Sprite','Ref'],
  unreal: [
    'UObject','AActor','APawn','ACharacter','AController',
    'APlayerController','AAIController','AGameMode','AGameModeBase',
    'AGameState','APlayerState','AHUD',
    'UActorComponent','USceneComponent','UPrimitiveComponent',
    'UMeshComponent','USkeletalMeshComponent','UStaticMeshComponent',
    'UCapsuleComponent','USphereComponent','UBoxComponent',
    'UGameInstance','ULocalPlayer',
    'UGameplayAbility','UAttributeSet','UAbilitySystemComponent',
    'UGameplayEffect','UGameplayTask',
    'UUserWidget','UWidget',
    'IAbilitySystemInterface','IInterface',
  ],
  dotnet:   ['Object','Component'],
  cpp:      [],
  axmol: [
    'Node','Scene','Layer','Sprite','Ref','Application',
    'Director','Action','Event','EventListener',
    'DrawNode','ClippingNode','MotionStreak',
    'Label','LabelTTF','Menu','MenuItem','MenuItemLabel',
    'ScrollView','ListView','PageView','TableView',
    'AudioEngine','SimpleAudioEngine',
  ],
}

// ★ private 포함 — Unity lifecycle은 private으로 선언하는 게 일반적
const LIFECYCLE: Record<EngineProfile, string[]> = {
  auto:     [],
  unity:    ['Awake','Start','Update','FixedUpdate','LateUpdate','OnEnable','OnDisable',
             'OnDestroy','OnTriggerEnter','OnTriggerExit','OnCollisionEnter','OnCollisionExit',
             'OnApplicationPause','OnApplicationFocus','Reset','OnValidate',
             'OnBecameVisible','OnBecameInvisible','OnDrawGizmos'],
  cocos2dx: ['init','onEnter','onExit','update','draw',
             'onEnterTransitionDidFinish','onExitTransitionDidStart','cleanup'],
  unreal: [
    'BeginPlay','EndPlay','Tick','PostInitializeComponents',
    'BeginDestroy','PostLoad','OnConstruction','Destroyed',
    'InitializeComponent','UninitializeComponent','OnRegister','OnUnregister',
    'ActivateAbility','EndAbility','CancelAbility','CommitAbility','CanActivateAbility',
    'PostGameplayEffectExecute','PreAttributeChange','PostAttributeChange',
    'SetupPlayerInputComponent','PossessedBy','UnPossessed','OnRep_PlayerState',
    'NativeConstruct','NativeDestruct','NativeTick','NativeOnInitialized',
  ],
  dotnet:   ['Main','Dispose','OnStart','OnStop','Initialize','Finalize'],
  cpp:      ['main','init','update','draw','cleanup'],
  axmol: ['init','onEnter','onExit','update','draw',
          'onEnterTransitionDidFinish','onExitTransitionDidStart','cleanup',
          'onTouchBegan','onTouchMoved','onTouchEnded','onTouchCancelled'],
}

type ClassType = 'engine_base' | 'engine_derived' | 'project'

function classifyClass(name: string, bases: string[], profile: EngineProfile, custom: string[]): ClassType {
  const eb = [...(ENGINE_BASES[profile] ?? []), ...custom]
  if (eb.includes(name)) return 'engine_base'
  if (bases.some(b => eb.includes(b))) return 'engine_derived'
  return 'project'
}

// Labels are resolved at render time via t()
const TYPE_BADGE_KEYS = {
  engine_base:    { icon: '🔴', color: 'text-red-400',     labelKey: 'engine_base_label'    as TranslationKey },
  engine_derived: { icon: '🟡', color: 'text-yellow-400',  labelKey: 'engine_derived_label' as TranslationKey },
  project:        { icon: '🟢', color: 'text-emerald-400', labelKey: 'project_label'        as TranslationKey },
}

// ── 시그니처 포맷 ─────────────────────────────────────────────
function sig(m: ClassMethod): string {
  const params = m.params.length === 0 ? ''
    : m.params.slice(0, 4).join(', ') + (m.params.length > 4 ? ', …' : '')
  const ret = m.ret && m.ret !== 'void' ? ` → ${m.ret}` : ' → void'
  return `(${params})${ret}`
}

// ── private 토글 ─────────────────────────────────────────────
function PrivateToggle({ count, children }: { count: number; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const { t } = useApp()
  if (count === 0) return null
  return (
    <div className="mt-2">
      <button onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 py-1">
        {open ? <ChevronDown size={12}/> : <ChevronRight size={12}/>}
        {t('private_toggle')} ({count})
      </button>
      {open && <div className="mt-1">{children}</div>}
    </div>
  )
}

// ── 테이블 (가로 폭 풀 활용, 스크롤 가능) ────────────────────
function FieldTable({ fields, dim = false }: { fields: ClassField[]; dim?: boolean }) {
  if (fields.length === 0) return null
  return (
    <table className="w-full text-sm border-collapse">
      <tbody>
        {fields.map(f => (
          <tr key={f.name + f.access}
            className={`border-b border-gray-800 hover:bg-gray-800/50 ${dim ? 'opacity-60' : ''}`}>
            <td className="py-1 px-2 text-emerald-400 whitespace-nowrap w-2/5">{f.name}</td>
            <td className="py-1 px-2 text-gray-400 break-all">{f.type}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function MethodTable({ methods, lifecycleMethods, dim = false }: {
  methods: ClassMethod[]; lifecycleMethods: string[]; dim?: boolean
}) {
  if (methods.length === 0) return null
  return (
    <table className="w-full text-sm border-collapse">
      <tbody>
        {methods.map(m => (
          <tr key={m.name + m.access}
            className={`border-b border-gray-800 hover:bg-gray-800/50 ${dim ? 'opacity-60' : ''}`}>
            <td className="py-1 px-2 whitespace-nowrap w-2/5">
              <span className={dim ? 'text-gray-500' : 'text-blue-400'}>
                {m.isAsync && <span className="text-yellow-500 mr-1 text-xs">⏱</span>}
                {lifecycleMethods.includes(m.name) && <span className="text-yellow-400 mr-1 text-xs">⚡</span>}
                {m.name}
              </span>
            </td>
            <td className="py-1 px-2 font-mono text-xs text-gray-500 break-all">{sig(m)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

interface Props { onFlowReady: () => void }

export default function ClassBrowser({ onFlowReady }: Props) {
  const {
    scriptsPath, projectInfo, selectedClass, setSelectedClass,
    setFlowData, setBreadcrumb, depth, focusClasses, setSelectedNode,
    getCache, setCache, engineProfile, customBaseClasses, t,
  } = useApp()

  const [classes,     setClasses]    = useState<Record<string, ClassInfo>>({})
  const [query,       setQuery]      = useState('')
  const [methodQuery, setMethodQuery] = useState('')
  const [loading,     setLoading]    = useState(false)
  const [analyzing,   setAnalyzing]  = useState(false)
  const [prefabRef,   setPrefabRef]  = useState<(PrefabRef & { class_name: string }) | null>(null)
  const [loadingRef,  setLoadingRef] = useState(false)
  const [bpRef,        setBpRef]        = useState<(BlueprintRef & { class_name: string }) | null>(null)
  const [bpLoading,    setBpLoading]    = useState(false)
  const [bpMapping,    setBpMapping]    = useState<string>('')
  const [bpMapLoading, setBpMapLoading] = useState(false)
  // Lint
  const [lintIssues,  setLintIssues]  = useState<LintIssue[]>([])
  const [lintLoading, setLintLoading] = useState(false)
  const [lintOpen,    setLintOpen]    = useState(false)
  // Describe / inheritance chain (Phase 2-4)
  const [describeResult,    setDescribeResult]    = useState<DescribeResult | null>(null)
  // Method Logic (Phase 2-3)
  const [methodLogic,       setMethodLogic]       = useState<ExplainMethodResult | null>(null)
  const [methodLogicLoading,setMethodLogicLoading]= useState(false)
  const [logicMethod,       setLogicMethod]       = useState<string | null>(null)

  useEffect(() => {
    if (!selectedClass || !scriptsPath || projectInfo?.kind !== 'UNREAL') {
      setBpRef(null); setBpLoading(false)
      setBpMapping(''); setBpMapLoading(false)
      return
    }
    setBpRef(null); setBpLoading(true)
    ue5Api.getClassBlueprintRefs(scriptsPath, selectedClass)
      .then(setBpRef)
      .catch(() => setBpRef(null))
      .finally(() => setBpLoading(false))

    // BP 매핑 상세 (K2 오버라이드, 변수, 태그)
    setBpMapping(''); setBpMapLoading(true)
    ue5Api.getBlueprintMapping(scriptsPath, selectedClass)
      .then(r => setBpMapping(r.result))
      .catch(() => setBpMapping(''))
      .finally(() => setBpMapLoading(false))
  }, [selectedClass, scriptsPath, projectInfo])

  // describe 결과 (inheritance_chain 포함) — selectedClass 변경 시 갱신
  useEffect(() => {
    if (!selectedClass || !scriptsPath) { setDescribeResult(null); return }
    projectApi.describe(scriptsPath, selectedClass)
      .then(setDescribeResult)
      .catch(() => setDescribeResult(null))
    setMethodLogic(null); setLogicMethod(null)
  }, [selectedClass, scriptsPath])

  // 클래스 목록 캐시
  useEffect(() => {
    if (!scriptsPath) return
    const cached = getCache(scriptsPath).classMap
    if (cached) { setClasses(cached); return }
    setLoading(true)
    classesApi.list(scriptsPath)
      .then(d => { setClasses(d.classes); setCache(scriptsPath, { classMap: d.classes }) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [scriptsPath])

  // 프리팹 역참조 캐시
  useEffect(() => {
    if (!selectedClass || !scriptsPath || projectInfo?.kind !== 'UNITY') { setPrefabRef(null); return }
    const cached = getCache(scriptsPath).prefabRefs?.[selectedClass]
    if (cached) { setPrefabRef({ ...cached, class_name: selectedClass }); return }
    setLoadingRef(true)
    unityApi.getClassRefs(scriptsPath, selectedClass)
      .then(ref => {
        setPrefabRef(ref)
        const ex = getCache(scriptsPath).prefabRefs ?? {}
        setCache(scriptsPath, { prefabRefs: { ...ex, [selectedClass]: ref } })
      })
      .catch(() => setPrefabRef(null))
      .finally(() => setLoadingRef(false))
  }, [selectedClass, scriptsPath, projectInfo])

  async function runFlow(cls: string, method: string) {
    setAnalyzing(true)
    try {
      const data = await flowApi.analyze(scriptsPath, cls, method, depth, focusClasses)
      setFlowData(data); setBreadcrumb([{ cls, method }]); setSelectedNode(null)
      onFlowReady()
    } catch (e) { console.error(e) }
    finally { setAnalyzing(false) }
  }

  async function runLint() {
    setLintLoading(true); setLintOpen(true)
    try {
      const res = await projectApi.lint(scriptsPath)
      setLintIssues(res.issues)
    } catch (e) { console.error(e) }
    finally { setLintLoading(false) }
  }

  const profile    = engineProfile
  const lcMethods  = LIFECYCLE[profile] ?? []
  const classNames = Object.keys(classes).sort()
  const filtered   = query
    ? classNames.filter(c => c.toLowerCase().includes(query.toLowerCase()))
    : classNames

  const cls     = selectedClass ? classes[selectedClass] : null
  const methods = cls?.methods ?? []
  const fields  = cls?.fields  ?? []

  const lifecycle   = methods.filter(m => lcMethods.includes(m.name))
  const lcNames     = new Set(lifecycle.map(m => m.name))

  const pubFields   = fields.filter(f => f.access === 'public')
  const privFields  = fields.filter(f => f.access !== 'public')

  const pubOther    = methods.filter(m => m.access === 'public'  && !lcNames.has(m.name)
                        && (!methodQuery || m.name.toLowerCase().includes(methodQuery.toLowerCase())))
  const privOther   = methods.filter(m => m.access !== 'public'  && !lcNames.has(m.name)
                        && (!methodQuery || m.name.toLowerCase().includes(methodQuery.toLowerCase())))

  // resolved TYPE_BADGE with translated labels
  const TYPE_BADGE = Object.fromEntries(
    Object.entries(TYPE_BADGE_KEYS).map(([k, v]) => [k, { ...v, label: t(v.labelKey) }])
  ) as Record<string, { icon: string; color: string; label: string }>

  if (!scriptsPath) return (
    <div className="flex items-center justify-center h-full text-gray-500 text-base">
      {t('class_no_path')}
    </div>
  )

  return (
    <div className="flex h-full overflow-hidden">

      {/* 클래스 목록 (고정 너비) */}
      <div className="w-64 shrink-0 border-r border-gray-800 flex flex-col">
        <div className="p-3 border-b border-gray-800">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-2.5 text-gray-500"/>
            <input className="input pl-8 text-sm" placeholder={t('class_search_placeholder')}
              value={query} onChange={e => setQuery(e.target.value)}/>
          </div>
        <div className="flex items-center justify-between mt-1">
            <p className="text-xs text-gray-500">
              {filtered.length}/{classNames.length}개
              {loading && <span className="ml-1 animate-pulse">{t('parsing')}</span>}
            </p>
            <div className="flex items-center gap-1.5">
              <button onClick={runLint} disabled={lintLoading}
                title={t('scan_title')}
                className="flex items-center gap-1 text-xs px-2 py-0.5 rounded
                           bg-orange-900 hover:bg-orange-800 border border-orange-700
                           text-orange-200 disabled:opacity-50 transition-colors">
                <ShieldAlert size={11}/>
                {lintLoading ? t('lint_scanning') : 'Lint'}
              </button>
              <div className="flex gap-1.5 text-xs">
                <span>🟢</span><span>🟡</span><span>🔴</span>
              </div>
            </div>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {filtered.slice(0, 200).map(name => {            const bases = classes[name]?.bases ?? []
            const ct    = classifyClass(name, bases, profile, customBaseClasses)
            const bx    = TYPE_BADGE[ct]
            return (
              <button key={name}
                onClick={() => { setSelectedClass(name); setMethodQuery('') }}
                className={`w-full text-left text-sm px-2 py-1 rounded flex items-center gap-1.5 transition-colors
                  ${selectedClass === name
                    ? 'bg-emerald-900 text-emerald-300 border border-emerald-700'
                    : 'text-gray-300 hover:bg-gray-800'}`}>
                <span className="shrink-0 text-xs">{bx.icon}</span>
                <span className="truncate">{name}</span>
              </button>
            )
          })}
          {filtered.length > 200 && (
            <p className="text-xs text-gray-500 text-center py-2">{t('search_narrow')} ({filtered.length})</p>
          )}
        </div>

        {/* ── Lint 결과 패널 ── */}
        {lintOpen && (
          <div className="border-t border-gray-800 shrink-0 flex flex-col" style={{ maxHeight: 300 }}>
            <div className="flex items-center justify-between px-3 py-2 bg-orange-950/40
                            border-b border-orange-900 shrink-0">
              <span className="text-xs font-semibold text-orange-300 flex items-center gap-1.5">
                <ShieldAlert size={12}/> {t('lint_results')}
                {!lintLoading && (
                  <span className="ml-1 text-gray-400">
                    {lintIssues.length === 0 ? t('lint_none') : `${lintIssues.length}`}
                  </span>
                )}
              </span>
              <button onClick={() => setLintOpen(false)}
                className="text-xs text-gray-500 hover:text-gray-300">✕</button>
            </div>
            <div className="overflow-y-auto flex-1">
              {lintLoading && (
                <p className="text-xs text-gray-500 px-3 py-2 animate-pulse">{t('lint_scanning')}</p>
              )}
              {!lintLoading && lintIssues.length === 0 && (
                <p className="text-xs text-emerald-400 px-3 py-2">{t('lint_no_issues')}</p>
              )}
              {!lintLoading && lintIssues.map((issue, i) => {
                const sevCls = issue.severity === 'Error'
                  ? 'bg-red-900/60 border-red-800 text-red-300'
                  : issue.severity === 'Warning'
                    ? 'bg-yellow-900/40 border-yellow-800 text-yellow-300'
                    : 'bg-blue-900/30 border-blue-800 text-blue-300'
                const sevIcon = issue.severity === 'Error' ? '✕'
                  : issue.severity === 'Warning' ? '⚠' : 'ℹ'
                const ruleColor = issue.rule_id.startsWith('UE5-GAS') ? 'text-purple-400'
                  : issue.rule_id.startsWith('UE5-NET') ? 'text-cyan-400'
                  : issue.rule_id.startsWith('UE5') ? 'text-orange-400'
                  : issue.rule_id.startsWith('UNI') ? 'text-emerald-400'
                  : 'text-gray-500'
                return (
                  <div key={i}
                    onClick={() => setSelectedClass(issue.class_name)}
                    className={`px-3 py-2 border-b border-gray-800 hover:bg-gray-800/60
                               cursor-pointer transition-colors`}>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className={`inline-flex items-center justify-center
                                        w-4 h-4 rounded text-xs font-bold shrink-0
                                        ${sevCls}`}>
                        {sevIcon}
                      </span>
                      <span className="text-xs text-gray-300 font-medium truncate flex-1">
                        {issue.class_name}
                        {issue.method_name && (
                          <span className="text-gray-500">.{issue.method_name}</span>
                        )}
                      </span>
                      <span className={`text-xs font-mono shrink-0 ${ruleColor}`}>
                        {issue.rule_id}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5 ml-5 leading-relaxed">
                      {issue.message}
                    </p>
                    {issue.suggestion && (
                      <p className="text-xs text-blue-400/70 mt-0.5 ml-5">
                        💡 {issue.suggestion}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* 상세 패널 — 가로 폭 풀 활용 */}
      <div className="flex-1 overflow-y-auto p-5">
        {!selectedClass ? (
          <div className="flex items-center justify-center h-full text-gray-500 text-base">
            {t('class_select')}
          </div>
        ) : cls ? (() => {
          const ct  = classifyClass(selectedClass, cls.bases, profile, customBaseClasses)
          const bx  = TYPE_BADGE[ct]
          return (
            <div className="space-y-5">

              {/* 헤더 */}
              <div className="flex items-start gap-3">
                <span className={`text-2xl mt-0.5 shrink-0 ${bx.color}`} title={bx.label}>
                  {bx.icon}
                </span>
                <div>
                  <h2 className="text-xl font-bold text-white flex flex-wrap items-center gap-2">
                    {selectedClass}
                    <span className="text-sm text-gray-500 font-normal">{cls.kind}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded bg-gray-800 border border-gray-700 ${bx.color}`}>
                      {bx.label}
                    </span>
                  </h2>
                  {/* 상속 체인 breadcrumb (describe 결과 기반) */}
                  {describeResult && describeResult.inheritance_chain.length > 1 ? (
                    <div className="flex flex-wrap items-center gap-1 mt-1">
                      {describeResult.inheritance_chain.map((cls2, i) => (
                        <span key={cls2} className="flex items-center gap-1">
                          {i > 0 && <ChevronRight size={12} className="text-gray-600 shrink-0" />}
                          <button
                            onClick={() => setSelectedClass(cls2)}
                            className="text-sm text-purple-400 hover:text-purple-300 hover:underline transition-colors">
                            {cls2}
                          </button>
                        </span>
                      ))}
                      {describeResult.also_implements.length > 0 && (
                        <span className="text-xs text-gray-500 ml-1">
                          +{describeResult.also_implements.join(', ')}
                        </span>
                      )}
                    </div>
                  ) : cls.bases.length > 0 ? (
                    <p className="text-sm text-gray-400 mt-0.5">
                      {t('inheritance')}: {cls.bases.map(b => (
                        <button key={b}
                          onClick={() => setSelectedClass(b)}
                          className="text-purple-400 hover:text-purple-300 hover:underline mr-2 transition-colors">
                          {b}
                        </button>
                      ))}
                    </p>
                  ) : null}
                </div>
              </div>

              {/* 프리팹 역참조 */}
              {projectInfo?.kind === 'UNITY' && (
                <div className="card p-3">
                  <h3 className="text-sm font-semibold text-gray-300 mb-2">{t('prefab_usage')}</h3>
                  {loadingRef
                    ? <p className="text-sm text-gray-500 animate-pulse">{t('loading')}</p>
                    : prefabRef && prefabRef.total > 0 ? (
                      <div className="space-y-0.5">
                        {prefabRef.prefabs.map(p => (
                          <p key={p} className="text-sm text-blue-400" title={p}>
                            📦 <span className="font-medium">{p.split(/[\\/]/).pop()}</span>
                            <span className="text-gray-600 ml-2 text-xs">{p}</span>
                          </p>
                        ))}
                        {prefabRef.scenes.map(s => (
                          <p key={s} className="text-sm text-yellow-400" title={s}>
                            🎬 <span className="font-medium">{s.split(/[\\/]/).pop()}</span>
                            <span className="text-gray-600 ml-2 text-xs">{s}</span>
                          </p>
                        ))}
                      </div>
                    ) : <p className="text-sm text-gray-500">{t('no_prefab')}</p>
                  }
                </div>
              )}

              {projectInfo?.kind === 'UNREAL' && (
              <div className="card p-3">
                <h3 className="text-sm font-semibold text-gray-300 mb-2 flex items-center gap-2">
                  {t('bp_impl')}
                  {bpRef && bpRef.total > 0 && (
                    <span className="text-xs bg-blue-900 text-blue-300 px-1.5 py-0.5 rounded-full">
                      {bpRef.total}개
                    </span>
                  )}
                </h3>
                {/* 파일 목록 (빠른 참조) */}
                {bpLoading ? (
                  <p className="text-sm text-gray-500 animate-pulse">{t('loading')}</p>
                ) : bpRef && bpRef.total > 0 ? (
                  <div className="space-y-0.5 mb-3">
                    {bpRef.blueprints.map(p => (
                      <p key={p} className="text-sm text-blue-400" title={p}>
                        📋 <span className="font-medium">{p.split(/[\\/]/).pop()}</span>
                        <span className="text-gray-600 ml-2 text-xs">{p}</span>
                      </p>
                    ))}
                    {bpRef.maps.map(m => (
                      <p key={m} className="text-sm text-yellow-400" title={m}>
                        🗺️ <span className="font-medium">{m.split(/[\\/]/).pop()}</span>
                        <span className="text-gray-600 ml-2 text-xs">{m}</span>
                      </p>
                    ))}
                  </div>
                ) : !bpLoading && (
                  <p className="text-sm text-gray-500 mb-2">{t('no_bp')}</p>
                )}
                {/* BP 매핑 상세 (K2 오버라이드, 변수, GameplayTag) */}
                {bpMapLoading && (
                  <p className="text-xs text-gray-500 animate-pulse">{t('bp_mapping_loading')}</p>
                )}
                {!bpMapLoading && bpMapping && !bpMapping.startsWith('Error') && (
                  <BpMappingDetail text={bpMapping} />
                )}
              </div>
            )}

              {/* 필드 + 메서드 — 세로 배치로 가로 폭 최대 활용 */}
              <div className="grid grid-cols-2 gap-4">

                {/* 필드 */}
                <div className="card overflow-hidden">
                  <div className="px-3 py-2 border-b border-gray-700 bg-gray-800/50">
                    <h3 className="text-sm font-semibold text-gray-200">
                      {t('fields')}
                      <span className="text-gray-500 font-normal ml-1.5">({fields.length})</span>
                    </h3>
                  </div>
                  <div className="overflow-y-auto" style={{ maxHeight: 260 }}>
                    <FieldTable fields={pubFields} />
                    <PrivateToggle count={privFields.length}>
                      <FieldTable fields={privFields} dim />
                    </PrivateToggle>
                  </div>
                </div>

                {/* 메서드 */}
                <div className="card overflow-hidden">
                  <div className="px-3 py-2 border-b border-gray-700 bg-gray-800/50">
                    <h3 className="text-sm font-semibold text-gray-200">
                      {t('methods')}
                      <span className="text-gray-500 font-normal ml-1.5">({methods.length})</span>
                    </h3>
                  </div>
                  <div className="overflow-y-auto" style={{ maxHeight: 260 }}>
                    <MethodTable methods={methods.filter(m => m.access === 'public')} lifecycleMethods={lcMethods} />
                    <PrivateToggle count={methods.filter(m => m.access !== 'public').length}>
                      <MethodTable methods={methods.filter(m => m.access !== 'public')} lifecycleMethods={lcMethods} dim />
                    </PrivateToggle>
                  </div>
                </div>

              </div>

              {/* 흐름 분석 */}
              <div className="card p-4">
                <h3 className="text-base font-semibold text-gray-100 mb-4">
                  {t('flow_analysis')}
                  {analyzing && <span className="text-sm text-emerald-400 ml-2 animate-pulse">{t('analyzing')}</span>}
                </h3>

                {/* 라이프사이클 진입점 — private 포함 */}
                {lifecycle.length > 0 && (
                  <div className="mb-5">
                    <p className="text-sm text-yellow-400 font-medium mb-2.5 flex items-center gap-1.5">
                      <Zap size={14}/> {t('lifecycle_entry')}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {lifecycle.map(m => (
                        <button key={m.name}
                          onClick={() => runFlow(selectedClass, m.name)}
                          disabled={analyzing}
                          title={sig(m)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded
                                     bg-yellow-900 hover:bg-yellow-800 border border-yellow-700
                                     text-yellow-200 text-sm font-medium transition-colors
                                     disabled:opacity-50">
                          <Zap size={12} className="text-yellow-400"/>
                          {m.name}
                          <span className="font-mono text-xs text-yellow-400/70">{sig(m)}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* 메서드 검색 */}
                <div>
                  <div className="relative mb-3">
                    <Search size={14} className="absolute left-2.5 top-2.5 text-gray-500"/>
                    <input className="input pl-8 text-sm" placeholder={t('method_search_placeholder')}
                      value={methodQuery} onChange={e => setMethodQuery(e.target.value)}/>
                  </div>

                  {/* public 메서드 그리드 */}
                  {pubOther.length > 0 && (
                    <div className="mb-3">
                      <p className="text-xs text-gray-500 mb-2 uppercase tracking-wide">public</p>
                      <div className="grid grid-cols-2 gap-1.5 max-h-52 overflow-y-auto pr-1">
                        {pubOther.slice(0, 60).map(m => (
                          <button key={m.name}
                            onClick={() => runFlow(selectedClass, m.name)}
                            disabled={analyzing}
                            title={`${m.name}${sig(m)}`}
                            className="text-left flex flex-col gap-0.5 px-3 py-2 rounded
                                       bg-gray-700 hover:bg-gray-600 border border-gray-600
                                       hover:border-emerald-700 transition-colors disabled:opacity-50">
                            <span className="flex items-center gap-1 text-sm text-gray-100 truncate w-full">
                              {m.isAsync && <span className="text-yellow-500 shrink-0">⏱</span>}
                              <span className="truncate font-medium">{m.name}</span>
                            </span>
                            <span className="font-mono text-xs text-gray-500 truncate w-full">{sig(m)}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* private 메서드 */}
                  {privOther.length > 0 && (
                    <PrivateToggle count={privOther.length}>
                      <div className="grid grid-cols-2 gap-1.5 max-h-44 overflow-y-auto pr-1 mt-1">
                        {privOther.slice(0, 40).map(m => (
                          <button key={m.name}
                            onClick={() => runFlow(selectedClass, m.name)}
                            disabled={analyzing}
                            title={`${m.name}${sig(m)}`}
                            className="text-left flex flex-col gap-0.5 px-3 py-2 rounded
                                       bg-gray-800 hover:bg-gray-700 border border-gray-700
                                       transition-colors disabled:opacity-50">
                            <span className="flex items-center gap-1 text-sm text-gray-400 truncate w-full">
                              <span className="text-gray-600 shrink-0">🔒</span>
                              {m.isAsync && <span className="text-yellow-600 shrink-0">⏱</span>}
                              <span className="truncate">{m.name}</span>
                            </span>
                            <span className="font-mono text-xs text-gray-600 truncate w-full">{sig(m)}</span>
                          </button>
                        ))}
                      </div>
                    </PrivateToggle>
                  )}

                  {/* Method Logic 빠른 분석 */}
                  <div className="mt-3">
                    <p className="text-xs text-gray-500 mb-2 uppercase tracking-wide">Method Logic</p>
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {[...lifecycle, ...pubOther].slice(0, 16).map(m => (
                        <button key={m.name}
                          onClick={async () => {
                            setLogicMethod(m.name)
                            setMethodLogic(null)
                            setMethodLogicLoading(true)
                            try {
                              const res = await projectApi.explainMethodLogic(scriptsPath, selectedClass, m.name)
                              setMethodLogic(res)
                            } catch { setMethodLogic(null) }
                            finally { setMethodLogicLoading(false) }
                          }}
                          className={`text-xs px-2 py-1 rounded border transition-colors
                            ${logicMethod === m.name
                              ? 'border-violet-500 text-violet-300 bg-violet-950'
                              : 'border-gray-700 text-gray-400 hover:border-gray-500 hover:text-gray-300'}`}>
                          {m.name}
                        </button>
                      ))}
                    </div>
                    {methodLogicLoading && (
                      <p className="text-xs text-gray-500 animate-pulse">analyzing {logicMethod}…</p>
                    )}
                    {methodLogic && !methodLogicLoading && (
                      <div className="rounded border border-violet-800 bg-violet-950/30 p-3 space-y-1">
                        <p className="text-xs font-semibold text-violet-300 mb-1.5">{logicMethod}()</p>
                        {methodLogic.items.length === 0 ? (
                          <p className="text-xs text-gray-500">Linear sequence — no branching logic detected.</p>
                        ) : methodLogic.items.map((item, i) => {
                          const typeColor: Record<string, string> = {
                            guard: 'text-red-400', branch: 'text-yellow-400',
                            loop: 'text-blue-400', switch: 'text-cyan-400',
                            exception: 'text-orange-400', always: 'text-green-400',
                          }
                          const color = typeColor[item.type] ?? 'text-gray-400'
                          return (
                            <div key={i} className="flex gap-2 text-xs">
                              <span className={`shrink-0 w-16 font-mono uppercase ${color}`}>{item.type}</span>
                              <span className="text-gray-300 truncate" title={item.text}>{item.text}</span>
                            </div>
                          )
                        })}
                        {methodLogic.source_file && (
                          <p className="text-xs text-gray-600 mt-1 pt-1 border-t border-violet-800/50">
                            {methodLogic.source_file}
                          </p>
                        )}
                      </div>
                    )}
                  </div>

                </div>
              </div>

            </div>
          )
        })() : null}
      </div>
    </div>
  )
}

import { useState, useEffect } from 'react'
import dagre from '@dagrejs/dagre'
import {
  ReactFlow, Background, Controls, MiniMap,
  useNodesState, useEdgesState,
  type Node, type Edge, MarkerType, Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Search } from 'lucide-react'
import { useApp } from '../store'
// t() accessed via useApp()
import {
  projectApi, classesApi, unityApi, ue5Api, engineApi, engineAnalysisApi, analysisApi,
  type CouplingItem, type ClassInfo, type PrefabRef, type BlueprintRef,
  type DeadNode, type ImpactNode, type TestScopeFile, type LintFixIssue,
} from '../api/client'

// ── 상속 그래프 빌더 ─────────────────────────────────────────
function buildInheritanceGraph(target: string, classMap: Record<string, ClassInfo>) {
  const nodeSet = new Set<string>()
  const edgeSet = new Set<string>()
  const ns: Node[] = []
  const es: Edge[] = []

  function addNode(name: string, center = false) {
    if (nodeSet.has(name)) return
    nodeSet.add(name)
    ns.push({
      id: name, data: { label: name },
      position: { x: 0, y: 0 },
      style: {
        background: center ? '#1D9E75' : '#7F77DD', color: '#fff',
        border: center ? '2px solid #34D399' : '1px solid #6366F1',
        borderRadius: 8, fontSize: 12, padding: '6px 12px',
        fontWeight: center ? 700 : 400,
      },
    })
  }

  function findParents(cls: string, d: number) {
    if (d <= 0) return
    for (const b of classMap[cls]?.bases ?? []) {
      if (!classMap[b]) continue
      addNode(b)
      const key = `${cls}→${b}`
      if (!edgeSet.has(key)) {
        edgeSet.add(key)
        es.push({
          id: key, source: cls, target: b, label: 'extends',
          style: { stroke: '#7F77DD' },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#7F77DD' },
          labelStyle: { fontSize: 10, fill: '#9CA3AF' },
          labelBgStyle: { fill: '#1F2937' },
        })
      }
      findParents(b, d - 1)
    }
  }

  function findChildren(cls: string, d: number) {
    if (d <= 0) return
    for (const [name, data] of Object.entries(classMap)) {
      if (!data.bases.includes(cls)) continue
      addNode(name)
      const key = `${name}→${cls}`
      if (!edgeSet.has(key)) {
        edgeSet.add(key)
        es.push({
          id: key, source: name, target: cls, label: 'extends',
          style: { stroke: '#7F77DD' },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#7F77DD' },
          labelStyle: { fontSize: 10, fill: '#9CA3AF' },
          labelBgStyle: { fill: '#1F2937' },
        })
      }
      findChildren(name, d - 1)
    }
  }

  addNode(target, true)
  findParents(target, 3)
  findChildren(target, 3)

  // 단순 레이아웃
  const arr = Array.from(nodeSet)
  arr.forEach((name, i) => {
    const n = ns.find(x => x.id === name)!
    n.position = name === target
      ? { x: 280, y: 180 }
      : { x: (i % 4) * 200, y: Math.floor(i / 4) * 120 }
  })

  return { nodes: ns, edges: es }
}


// ── 결합도 탭 ────────────────────────────────────────────────
function CouplingTab({ scriptsPath }: { scriptsPath: string }) {
  const { getCache, setCache, t } = useApp()
  const [coupling, setCoupling] = useState<CouplingItem[]>([])
  const [cycles,   setCycles]   = useState<string[]>([])
  const [loading,  setLoading]  = useState(false)

  useEffect(() => {
    const cached = getCache(scriptsPath).scanResult
    if (cached) { setCoupling(cached.coupling); setCycles(cached.cycles); return }
    setLoading(true)
    projectApi.scan(scriptsPath, 50, true)
      .then(d => {
        setCoupling(d.coupling); setCycles(d.cycles)
        setCache(scriptsPath, { scanResult: d })
      })
      .finally(() => setLoading(false))
  }, [scriptsPath])

  const direct   = cycles.filter(c => c.split('→').length <= 2)
  const indirect = cycles.filter(c => c.split('→').length > 2)

  return (
    <div className="flex gap-6 p-4 h-full overflow-y-auto">
      <div className="flex-1 max-w-lg">
        <p className="text-xs text-gray-500 mb-3">
          {t('coupling_desc')}
          <span className="text-red-400 ml-1">{t('coupling_danger')}</span>
          <span className="text-yellow-400 ml-1">{t('coupling_warn')}</span>
          <span className="text-emerald-400 ml-1">{t('coupling_ok')}</span>
        </p>
        {loading && <p className="text-gray-500 text-sm animate-pulse">{t('coupling_analyzing')}</p>}
        <div className="space-y-1.5">
          {coupling.map((item, idx) => {
            const color = item.score >= 10 ? '#E24B4A' : item.score >= 5 ? '#EF9F27' : '#1D9E75'
            const rank  = item.rank ?? idx + 1
            return (
              <div key={item.name} className="flex items-center gap-3 py-1">
                <span className="text-xs text-gray-500 w-5 text-right">{rank}</span>
                <span className="text-sm w-44 truncate text-gray-200">{item.name}</span>
                <div className="flex items-center gap-1.5 flex-1">
                  <div className="h-1.5 rounded"
                    style={{ width: Math.min(item.score / 2 + 1, 20) * 8, background: color }} />
                  <span className="text-sm font-mono" style={{ color }}>{item.score}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="w-72 shrink-0">
        <h3 className="text-sm font-medium text-gray-300 mb-3">
          {t('cycle_label')}
          {cycles.length > 0 && (
            <span className="ml-2 bg-red-900 text-red-300 text-xs px-1.5 py-0.5 rounded-full">
              {cycles.length}
            </span>
          )}
        </h3>
        {cycles.length === 0
          ? <p className="text-emerald-400 text-sm">{t('cycle_none')}</p>
          : <>
            {direct.length > 0 && (
              <div className="mb-3">
                <p className="text-xs text-red-400 mb-1">{t('cycle_direct')} {direct.length}</p>
                {direct.map((c, i) => (
                  <div key={i} className="text-xs font-mono bg-red-950 border border-red-900
                                          rounded px-2 py-1 mb-1 text-gray-300">↻ {c}</div>
                ))}
              </div>
            )}
            {indirect.length > 0 && (
              <div>
                <p className="text-xs text-yellow-400 mb-1">{t('cycle_indirect')} {indirect.length}</p>
                {indirect.map((c, i) => (
                  <div key={i} className="text-xs font-mono bg-gray-900 border border-gray-700
                                          rounded px-2 py-1 mb-1 text-gray-400">↻ {c}</div>
                ))}
              </div>
            )}
          </>
        }
      </div>
    </div>
  )
}


// ── 상속 관계 탭 ─────────────────────────────────────────────
function InheritanceTab({
  scriptsPath,
  isUnreal,
}: {
  scriptsPath: string
  isUnreal:    boolean
}) {
  const { getCache, setCache, t } = useApp()
  const [classMap, setClassMap] = useState<Record<string, ClassInfo>>({})
  const [loading,  setLoading]  = useState(false)
  const [query,    setQuery]    = useState('')
  const [selected, setSelected] = useState('')
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  // UE5 블루프린트 역참조
  const [bpRef,     setBpRef]    = useState<BlueprintRef | null>(null)
  const [bpLoading, setBpLoading] = useState(false)

  useEffect(() => {
    const cached = getCache(scriptsPath).classMap
    if (cached) { setClassMap(cached); return }
    setLoading(true)
    classesApi.list(scriptsPath)
      .then(d => { setClassMap(d.classes); setCache(scriptsPath, { classMap: d.classes }) })
      .finally(() => setLoading(false))
  }, [scriptsPath])

  // UE5 블루프린트 역참조
  useEffect(() => {
    if (!selected || !isUnreal) { setBpRef(null); return }
    setBpLoading(true)
    ue5Api.getClassBlueprintRefs(scriptsPath, selected)
      .then(r => setBpRef(r.total > 0 ? r : null))
      .catch(() => setBpRef(null))
      .finally(() => setBpLoading(false))
  }, [selected, scriptsPath, isUnreal])

  const classesWithRel = Object.keys(classMap).filter(name => {
    const d = classMap[name]
    return d.bases.length > 0 || Object.values(classMap).some(x => x.bases.includes(name))
  }).sort()

  const filtered = query
    ? classesWithRel.filter(c => c.toLowerCase().includes(query.toLowerCase()))
    : classesWithRel

  function selectClass(name: string) {
    setSelected(name)
    const { nodes: ns, edges: es } = buildInheritanceGraph(name, classMap)
    setNodes(ns); setEdges(es)
  }

  const cls      = selected ? classMap[selected] : null
  const parents  = cls ? cls.bases.filter(b => classMap[b]) : []
  const children = selected
    ? Object.keys(classMap).filter(n => classMap[n].bases.includes(selected))
    : []

  return (
    <div className="flex h-full overflow-hidden">
      {/* 클래스 목록 */}
      <div className="w-56 shrink-0 border-r border-gray-800 flex flex-col">
        <div className="p-3 border-b border-gray-800">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-2.5 text-gray-500"/>
            <input className="input pl-8 text-xs" placeholder="Class..."
              value={query} onChange={e => setQuery(e.target.value)} />
          </div>
          <p className="text-xs text-gray-500 mt-1">
            {filtered.length} {loading && <span className="animate-pulse">{t('inh_loading')}</span>}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {filtered.slice(0, 150).map(name => (
            <button key={name} onClick={() => selectClass(name)}
              className={`w-full text-left text-xs px-2 py-1 rounded truncate
                ${selected === name
                  ? 'bg-purple-900 text-purple-200 border border-purple-700'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'}`}>
              {name}
            </button>
          ))}
        </div>
      </div>

      {/* 상세 패널 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-gray-500 text-sm">
            {t('inh_select')}
          </div>
        ) : (
          <>
            {/* 상속 정보 + UE5 블루프린트 */}
            <div className="p-3 border-b border-gray-800 flex gap-8 shrink-0 flex-wrap">
              <div>
                <p className="text-xs text-gray-500 mb-1">{t('inh_parent')}</p>
                {parents.length === 0
                  ? <p className="text-xs text-gray-600">{t('inh_none')}</p>
                  : parents.map(p => (
                    <button key={p} onClick={() => selectClass(p)}
                      className="text-xs text-purple-400 hover:text-purple-300 block">{p}</button>
                  ))}
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1">{t('inh_child')} ({children.length})</p>
                <div className="max-h-20 overflow-y-auto">
                  {children.length === 0
                    ? <p className="text-xs text-gray-600">{t('inh_none')}</p>
                    : children.slice(0, 20).map(c => (
                      <button key={c} onClick={() => selectClass(c)}
                        className="text-xs text-emerald-400 hover:text-emerald-300 block">{c}</button>
                    ))
                  }
                </div>
              </div>

              {/* UE5 블루프린트 사용처 */}
              {isUnreal && (
                <div>
                  <p className="text-xs text-gray-500 mb-1">{t('inh_bp_usage')}</p>
                  {bpLoading ? (
                    <p className="text-xs text-gray-600 animate-pulse">{t('inh_loading')}</p>
                  ) : bpRef && bpRef.total > 0 ? (
                    <div className="space-y-0.5 max-h-20 overflow-y-auto">
                      {(bpRef.blueprints ?? []).map(p => (
                        <p key={p} className="text-xs text-blue-400 truncate max-w-48" title={p}>
                          📋 {p.split(/[\\/]/).pop()}
                        </p>
                      ))}
                      {(bpRef.maps ?? []).map(m => (
                        <p key={m} className="text-xs text-yellow-400 truncate max-w-48" title={m}>
                          🗺️ {m.split(/[\\/]/).pop()}
                        </p>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-600">{t('inh_no_usage')}</p>
                  )}
                </div>
              )}
            </div>

            {/* ReactFlow 그래프 */}
            <div className="flex-1 min-h-0">
              {nodes.length > 1 ? (
                <ReactFlow
                  nodes={nodes} edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  fitView
                  attributionPosition="bottom-right"
                  style={{ background: '#111827' }}
                >
                  <Background color="#374151" gap={20}/>
                  <Controls/>
                </ReactFlow>
              ) : (
                <div className="flex items-center justify-center h-full text-gray-500 text-sm">
                  {t('inh_no_rel')}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}


// ── 프리팹 역참조 탭 (Unity) ─────────────────────────────────
function PrefabRefsTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [refs,     setRefs]    = useState<Record<string, PrefabRef>>({})
  const [loading,  setLoading] = useState(false)
  const [query,    setQuery]   = useState('')
  const [selected, setSelected] = useState('')
  const [totalCls, setTotalCls] = useState(0)

  useEffect(() => {
    setLoading(true)
    unityApi.getRefs(scriptsPath)
      .then(d => { setRefs(d.refs); setTotalCls(d.total_classes) })
      .catch(() => setRefs({}))
      .finally(() => setLoading(false))
  }, [scriptsPath])

  const used     = Object.entries(refs).sort((a, b) => b[1].total - a[1].total)
  const filtered = query ? used.filter(([n]) => n.toLowerCase().includes(query.toLowerCase())) : used
  const selRef   = selected ? refs[selected] : null

  return (
    <div className="flex h-full overflow-hidden">
      <div className="w-64 shrink-0 border-r border-gray-800 flex flex-col">
        <div className="p-3 border-b border-gray-800">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-2.5 text-gray-500"/>
            <input className="input pl-8 text-xs" placeholder={t('dep_class_ph')}
              value={query} onChange={e => setQuery(e.target.value)} />
          </div>
          <p className="text-xs text-gray-500 mt-1">
            {loading ? t('analyzing') : `${used.length}${t('count_unit')} ${t('dep_of_total')} ${totalCls}${t('count_unit')}`}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {filtered.slice(0, 100).map(([name, ref]) => (
            <button key={name} onClick={() => setSelected(name)}
              className={`w-full text-left text-xs px-2 py-1 rounded flex items-center gap-1
                ${selected === name
                  ? 'bg-blue-900 text-blue-200 border border-blue-700'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'}`}>
              <span className="truncate flex-1">{name}</span>
              <span className="text-gray-600 shrink-0">{ref.total}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-gray-500 text-sm">
            {t('inh_select')}
          </div>
        ) : selRef ? (
          <div className="max-w-lg space-y-4">
            <div>
              <h2 className="text-lg font-bold text-white">{selected}</h2>
              <p className="text-xs text-gray-500">GUID: {selRef.guid}</p>
            </div>
            {selRef.prefabs.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-300 mb-2">
                  {t('dep_prefabs_label')} ({selRef.prefabs.length}{t('count_unit')})
                </h3>
                {selRef.prefabs.map(p => (
                  <div key={p} className="text-xs py-1 border-b border-gray-800">
                    <span className="text-blue-400 font-medium">{p.split(/[\\/]/).pop()}</span>
                    <span className="text-gray-600 ml-2">{p}</span>
                  </div>
                ))}
              </div>
            )}
            {selRef.scenes.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-300 mb-2">
                  {t('dep_scenes_label')} ({selRef.scenes.length}{t('count_unit')})
                </h3>
                {selRef.scenes.map(s => (
                  <div key={s} className="text-xs py-1 border-b border-gray-800">
                    <span className="text-yellow-400 font-medium">{s.split(/[\\/]/).pop()}</span>
                    <span className="text-gray-600 ml-2">{s}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}


// ── 블루프린트 역참조 탭 (UE5) ───────────────────────────────
function BlueprintRefsTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [refs,     setRefs]    = useState<Record<string, BlueprintRef>>({})
  const [loading,  setLoading] = useState(false)
  const [query,    setQuery]   = useState('')
  const [selected, setSelected] = useState('')
  const [totalCls, setTotalCls] = useState(0)

  useEffect(() => {
    setLoading(true)
    ue5Api.getBlueprintRefs(scriptsPath)
      .then(d => { setRefs(d.refs); setTotalCls(d.total_classes) })
      .catch(() => setRefs({}))
      .finally(() => setLoading(false))
  }, [scriptsPath])

  const used     = Object.entries(refs).sort((a, b) => b[1].total - a[1].total)
  const filtered = query ? used.filter(([n]) => n.toLowerCase().includes(query.toLowerCase())) : used
  const selRef   = selected ? refs[selected] : null

  return (
    <div className="flex h-full overflow-hidden">
      <div className="w-64 shrink-0 border-r border-gray-800 flex flex-col">
        <div className="p-3 border-b border-gray-800">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-2.5 text-gray-500"/>
            <input className="input pl-8 text-xs" placeholder={t('dep_class_ph')}
              value={query} onChange={e => setQuery(e.target.value)} />
          </div>
          <p className="text-xs text-gray-500 mt-1">
            {loading ? t('analyzing') : `${used.length}${t('count_unit')} ${t('dep_of_total')} ${totalCls}${t('count_unit')}`}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {filtered.slice(0, 100).map(([name, ref]) => (
            <button key={name} onClick={() => setSelected(name)}
              className={`w-full text-left text-xs px-2 py-1 rounded flex items-center gap-1
                ${selected === name
                  ? 'bg-blue-900 text-blue-200 border border-blue-700'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'}`}>
              <span className="truncate flex-1">{name}</span>
              <span className="text-gray-600 shrink-0">{ref.total}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-gray-500 text-sm">
            {t('inh_select')}
          </div>
        ) : selRef ? (
          <div className="max-w-lg space-y-4">
            <h2 className="text-lg font-bold text-white">{selected}</h2>
            {selRef.blueprints.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-300 mb-2">
                  {t('dep_bp_label')} ({selRef.blueprints.length}{t('count_unit')})
                </h3>
                {selRef.blueprints.map(p => (
                  <div key={p} className="text-xs py-1 border-b border-gray-800">
                    <span className="text-blue-400 font-medium">{p.split(/[\\/]/).pop()}</span>
                    <span className="text-gray-600 ml-2">{p}</span>
                  </div>
                ))}
              </div>
            )}
            {selRef.maps.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-300 mb-2">
                  {t('dep_maps_label')} ({selRef.maps.length}{t('count_unit')})
                </h3>
                {selRef.maps.map(m => (
                  <div key={m} className="text-xs py-1 border-b border-gray-800">
                    <span className="text-yellow-400 font-medium">{m.split(/[\\/]/).pop()}</span>
                    <span className="text-gray-600 ml-2">{m}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}


// ── Dead Code 탭 ─────────────────────────────────────────────
function DeadCodeTab({ scriptsPath, isUnity }: { scriptsPath: string; isUnity: boolean }) {
  const { t } = useApp()
  const [nodes,   setNodes]   = useState<DeadNode[]>([])
  const [loading, setLoading] = useState(false)
  const [query,   setQuery]   = useState('')
  const [loaded,  setLoaded]  = useState(false)

  function load() {
    setLoading(true)
    // Unity는 include_refs=true로 프리팹 역참조 필터링 적용
    projectApi.scan(scriptsPath, 20, false, true, false, isUnity)
      .then(d => { setNodes(d.deadNodes ?? []); setLoaded(true) })
      .catch(() => setNodes([]))
      .finally(() => setLoading(false))
  }

  const filtered = query
    ? nodes.filter(n => n.name.toLowerCase().includes(query.toLowerCase())
                     || n.ns.toLowerCase().includes(query.toLowerCase()))
    : nodes

  return (
    <div className="flex flex-col h-full overflow-hidden p-4 gap-3">
      <div className="flex items-center gap-3 shrink-0">
        <div className="relative flex-1 max-w-sm">
          <Search size={13} className="absolute left-2.5 top-2.5 text-gray-500"/>
          <input className="input pl-8 text-sm" placeholder={t('dead_search_ph')}
            value={query} onChange={e => setQuery(e.target.value)}/>
        </div>
        <button onClick={load} disabled={loading}
          className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
          {loading ? t('analyzing') : loaded ? t('dead_reanalyze') : t('dead_analyze_btn')}
        </button>
        {loaded && (
          <span className="text-sm text-gray-400">
            {nodes.length === 0
              ? <span className="text-emerald-400">{t('dead_none_found')}</span>
              : <span className="text-yellow-400">{filtered.length} / {nodes.length}{t('count_unit')}</span>}
          </span>
        )}
      </div>

      {!loaded ? (
        <div className="flex items-center justify-center flex-1 text-gray-500 text-sm">
          {t('dead_hint')}
        </div>
      ) : nodes.length === 0 ? (
        <div className="flex items-center justify-center flex-1 text-emerald-400 text-sm">
          {t('dead_all_ok')}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-sm border-collapse">
            <thead className="sticky top-0 bg-gray-900">
              <tr className="text-left text-xs text-gray-500 border-b border-gray-700">
                <th className="py-2 px-3 w-1/3">{t('dead_col_class')}</th>
                <th className="py-2 px-3 w-1/4">{t('dead_col_ns')}</th>
                <th className="py-2 px-3">{t('dead_col_file')}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(n => (
                <tr key={n.name} className="border-b border-gray-800 hover:bg-gray-800/50">
                  <td className="py-1.5 px-3 text-yellow-300 font-medium">{n.name}</td>
                  <td className="py-1.5 px-3 text-gray-400">{n.ns || '—'}</td>
                  <td className="py-1.5 px-3 text-gray-500 text-xs font-mono truncate max-w-xs"
                      title={n.file}>{n.file}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}


// ── Impact 탭 ─────────────────────────────────────────────────
function ImpactTreeNode({ node, depth = 0 }: { node: ImpactNode; depth?: number }) {
  const [open, setOpen] = useState(depth < 2)
  const hasChildren = node.children.length > 0
  const indent = depth * 20

  return (
    <div>
      <div className="flex items-center gap-1.5 py-1 hover:bg-gray-800/50 rounded px-2 cursor-pointer"
           style={{ paddingLeft: indent + 8 }}
           onClick={() => hasChildren && setOpen(v => !v)}>
        {hasChildren
          ? <span className="text-gray-500 text-xs w-3">{open ? '▼' : '▶'}</span>
          : <span className="text-gray-700 text-xs w-3">•</span>}
        <span className={`text-sm font-medium ${depth === 0 ? 'text-emerald-300' : 'text-gray-200'}`}>
          {node.name}
        </span>
        {node.file && (
          <span className="text-xs text-gray-600 truncate ml-1" title={node.file}>
            {node.file.split(/[\\/]/).pop()}
          </span>
        )}
        {hasChildren && (
          <span className="text-xs text-gray-600 ml-1">({node.children.length})</span>
        )}
      </div>
      {open && hasChildren && node.children.map((child, i) => (
        <ImpactTreeNode key={`${child.name}-${i}`} node={child} depth={depth + 1}/>
      ))}
    </div>
  )
}

function ImpactTab({ scriptsPath }: { scriptsPath: string }) {
  const { getCache, setCache, t } = useApp()
  const [target,    setTarget]    = useState('')
  const [query,     setQuery]     = useState('')
  const [open,      setOpen]      = useState(false)
  const [depth,     setDepth]     = useState(3)
  const [tree,      setTree]      = useState<ImpactNode | null>(null)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState('')
  const [classList, setClassList] = useState<string[]>([])
  const [clsLoading, setClsLoading] = useState(false)

  // 클래스 목록 로드 (캐시 재사용)
  useEffect(() => {
    const cached = getCache(scriptsPath).classMap
    if (cached) { setClassList(Object.keys(cached).sort()); return }
    setClsLoading(true)
    classesApi.list(scriptsPath)
      .then(d => {
        setCache(scriptsPath, { classMap: d.classes })
        setClassList(Object.keys(d.classes).sort())
      })
      .catch(() => {})
      .finally(() => setClsLoading(false))
  }, [scriptsPath])

  const filtered = query
    ? classList.filter(c => c.toLowerCase().includes(query.toLowerCase()))
    : classList

  function select(name: string) {
    setTarget(name); setQuery(''); setOpen(false)
  }

  async function analyze() {
    if (!target) return
    setLoading(true); setError(''); setTree(null)
    try {
      const res = await projectApi.impact(scriptsPath, target, depth)
      setTree(res.tree)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? String(e))
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden p-4 gap-3">
      {/* 컨트롤 바 */}
      <div className="flex items-center gap-2 shrink-0 flex-wrap">

        {/* 드롭다운 */}
        <div className="relative">
          <button
            onClick={() => { setOpen(v => !v); setQuery('') }}
            className={`input text-sm w-64 text-left flex items-center justify-between gap-2
              ${target ? 'text-emerald-300' : 'text-gray-500'}`}>
            <span className="truncate">{target || (clsLoading ? t('loading') : t('impact_select_ph'))}</span>
            <span className="text-gray-500 shrink-0">{open ? '▲' : '▼'}</span>
          </button>

          {open && (
            <div className="absolute z-20 top-full left-0 mt-1 w-72
                            bg-gray-900 border border-gray-700 rounded shadow-xl"
                 style={{ maxHeight: 320 }}>
              {/* 검색창 */}
              <div className="p-2 border-b border-gray-700">
                <div className="relative">
                  <Search size={12} className="absolute left-2.5 top-2.5 text-gray-500"/>
                  <input
                    autoFocus
                    className="input pl-8 text-xs w-full"
                    placeholder={t('class_search_placeholder')}
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && filtered.length > 0) select(filtered[0])
                      if (e.key === 'Escape') setOpen(false)
                    }}
                  />
                </div>
                <p className="text-xs text-gray-600 mt-1 px-1">
                  {filtered.length} / {classList.length}{t('count_unit')}
                </p>
              </div>
              {/* 목록 */}
              <div className="overflow-y-auto" style={{ maxHeight: 240 }}>
                {filtered.slice(0, 150).map(name => (
                  <button key={name} onClick={() => select(name)}
                    className={`w-full text-left text-xs px-3 py-1.5 truncate transition-colors
                      ${name === target
                        ? 'bg-emerald-900 text-emerald-200'
                        : 'text-gray-300 hover:bg-gray-800'}`}>
                    {name}
                  </button>
                ))}
                {filtered.length > 150 && (
                  <p className="text-xs text-gray-600 text-center py-2">{t('search_narrow')}</p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Depth */}
        <div className="flex items-center gap-1.5 text-sm text-gray-400">
          <span>Depth</span>
          <select className="input text-sm w-16 py-1"
            value={depth} onChange={e => setDepth(Number(e.target.value))}>
            {[1,2,3,4,5].map(v => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>

        <button onClick={analyze} disabled={loading || !target}
          className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
          {loading ? t('analyzing') : t('impact_analyze_btn')}
        </button>

        <p className="text-xs text-gray-500">{t('impact_desc')}</p>
      </div>

      {error && (
        <div className="text-sm text-red-400 bg-red-950 border border-red-800 rounded px-3 py-2">
          {error}
        </div>
      )}

      {tree && (
        <div className="flex-1 overflow-y-auto border border-gray-800 rounded bg-gray-900/50 p-2">
          <ImpactTreeNode node={tree}/>
        </div>
      )}

      {!tree && !loading && !error && (
        <div className="flex items-center justify-center flex-1 text-gray-500 text-sm">
          {t('impact_hint')}
        </div>
      )}
    </div>
  )
}


// 마크다운 텍스트를 보기 좋게 렌더링하는 단순 컴포넌트
function MdResult({ text, loading }: { text: string; loading: boolean }) {
  const { t } = useApp()
  if (loading) return (
    <p className="text-gray-500 text-sm animate-pulse">{t('md_long_analyzing')}</p>
  )
  if (!text) return (
    <p className="text-gray-600 text-sm">{t('md_start_hint')}</p>
  )
  return (
    <div className="space-y-0.5">
      {text.split('\n').map((line, i) => {
        if (line.startsWith('# '))
          return <h2 key={i} className="text-base font-bold text-white mt-3 mb-1">{line.slice(2)}</h2>
        if (line.startsWith('## '))
          return <h3 key={i} className="text-sm font-semibold text-emerald-400 mt-3 mb-1 border-b border-gray-800 pb-1">{line.slice(3)}</h3>
        if (line.startsWith('### '))
          return <h4 key={i} className="text-sm font-medium text-yellow-400 mt-2 mb-0.5">{line.slice(4)}</h4>
        if (line.startsWith('- '))
          return <p key={i} className="text-sm text-gray-300 pl-3">• {line.slice(2)}</p>
        if (line.startsWith('  - '))
          return <p key={i} className="text-sm text-gray-400 pl-6">· {line.slice(4)}</p>
        if (line.startsWith('| '))
          return <p key={i} className="text-xs font-mono text-gray-400 pl-2">{line}</p>
        if (line.startsWith('```'))
          return null
        if (line.trim() === '') return <div key={i} className="h-1.5" />
        return <p key={i} className="text-sm text-gray-400">{line}</p>
      })}
    </div>
  )
}

// ── Unity Event 바인딩 탭 ─────────────────────────────────────
function UnityEventsTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [result,  setResult]  = useState('')
  const [loading, setLoading] = useState(false)
  const [filter,  setFilter]  = useState('')

  async function run() {
    setLoading(true)
    try {
      const res = await engineApi.unityEvents(scriptsPath, filter || undefined)
      setResult(res)
    } catch (e: any) {
      setResult(`Error: ${e?.message ?? e}`)
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-3 overflow-hidden">
      <div className="flex items-center gap-3 shrink-0 flex-wrap">
        <input className="input text-sm w-56" placeholder={t('unity_ev_filter_ph')}
          value={filter} onChange={e => setFilter(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()} />
        <button onClick={run} disabled={loading} className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
          {loading ? t('analyzing') : t('unity_ev_btn')}
        </button>
        <p className="text-xs text-gray-500">{t('unity_ev_desc')}</p>
      </div>
      <div className="flex-1 overflow-y-auto border border-gray-800 rounded bg-gray-900/50 p-4">
        <MdResult text={result} loading={loading} />
      </div>
    </div>
  )
}

// ── Unity Animator 탭 ─────────────────────────────────────────
function UnityAnimatorTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [result,  setResult]  = useState('')
  const [loading, setLoading] = useState(false)
  const [ctrlName, setCtrlName] = useState('')

  async function run() {
    setLoading(true)
    try {
      const res = await engineApi.unityAnimator(scriptsPath, ctrlName || undefined)
      setResult(res)
    } catch (e: any) {
      setResult(`Error: ${e?.message ?? e}`)
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-3 overflow-hidden">
      <div className="flex items-center gap-3 shrink-0 flex-wrap">
        <input className="input text-sm w-56" placeholder={t('unity_anim_filter_ph')}
          value={ctrlName} onChange={e => setCtrlName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()} />
        <button onClick={run} disabled={loading} className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
          {loading ? t('analyzing') : t('unity_anim_btn')}
        </button>
        <p className="text-xs text-gray-500">{t('unity_anim_desc')}</p>
      </div>
      <div className="flex-1 overflow-y-auto border border-gray-800 rounded bg-gray-900/50 p-4">
        <MdResult text={result} loading={loading} />
      </div>
    </div>
  )
}

// ── UE5 GAS 탭 ───────────────────────────────────────────────
const GAS_NODE_COLORS: Record<string, string> = {
  ability:       '#1D6E4E',  // 초록  — C++ GA
  effect:        '#6B3A8A',  // 보라  — C++ GE
  attribute_set: '#1A4A8A',  // 파랑  — C++ AS
  tag:           '#7A4500',  // 주황  — GameplayTag
  bp_ability:    '#0E4A30',  // 진한초록 — Blueprint GA
  bp_effect:     '#3D1F60',  // 진한보라 — Blueprint GE
  bp_attr_set:   '#0A2A5A',  // 진한파랑 — Blueprint AS
}
const GAS_NODE_LABELS: Record<string, string> = {
  ability:    'GA',     effect:      'GE',  attribute_set: 'AS',   tag: 'Tag',
  bp_ability: 'BP·GA',  bp_effect:  'BP·GE',  bp_attr_set: 'BP·AS',
}

// 노드 타입별 테두리 색 (BP 노드는 점선 강조)
const GAS_NODE_BORDERS: Record<string, string> = {
  bp_ability:  '2px dashed #34D399',
  bp_effect:   '2px dashed #A78BFA',
  bp_attr_set: '2px dashed #60A5FA',
}

function GasGraph({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [gasNodes, setGasNodes, onGasNodesChange] = useNodesState<Node>([])
  const [gasEdges, setGasEdges, onGasEdgesChange] = useEdgesState<Edge>([])
  const [summary,  setSummary]  = useState<Record<string, number> | null>(null)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const data = await engineApi.ue5GasGraph(scriptsPath)
      if (data.error) { setError(data.error); return }

      // ReactFlow 노드 생성 (라벨 길이 기반 동적 너비)
      const GAS_CHAR_W = 7, GAS_PAD = 32, GAS_NODE_MIN = 110, GAS_NODE_MAX = 280
      const calcGasNodeW = (lbl: string) =>
        Math.min(GAS_NODE_MAX, Math.max(GAS_NODE_MIN, Math.ceil(lbl.length * GAS_CHAR_W) + GAS_PAD))

      const rfNodes: Node[] = data.nodes.map((n) => {
        const label = `[${GAS_NODE_LABELS[n.type] ?? n.type}] ${n.label}`
        const nodeW = calcGasNodeW(label)
        return {
          id:   n.id,
          data: { label, nodeWidth: nodeW },
          position: { x: 0, y: 0 },
          style: {
            background:   GAS_NODE_COLORS[n.type] ?? '#374151',
            color:        '#fff',
            border:       GAS_NODE_BORDERS[n.type] ?? '1px solid rgba(255,255,255,0.15)',
            borderRadius: 8,
            fontSize:     12,
            padding:      '5px 12px',
            width:        nodeW,
            opacity:      n.type.startsWith('bp_') ? 0.88 : 1,
          },
          sourcePosition: Position.Bottom,
          targetPosition: Position.Top,
        }
      })

      // ReactFlow 엣지 생성
      const GAS_EDGE_COLORS: Record<string, string> = {
        applies:   '#A78BFA',  // 보라 — GA→GE
        owns:      '#60A5FA',  // 파랑 — ASC→AS
        uses_tag:  '#FCD34D',  // 노랑 — GA→Tag
        bp_impl:   '#34D399',  // 초록 — C++ GA→BP GA
        uses_attr: '#60A5FA',  // 파랑 — BP GA→BP AS
      }
      const rfEdges: Edge[] = data.edges.map(e => {
        const color = GAS_EDGE_COLORS[e.relation] ?? '#6B7280'
        const isBpImpl = e.relation === 'bp_impl'
        return {
          id:       `${e.from}→${e.to}`,
          source:   e.from,
          target:   e.to,
          label:    e.relation,
          animated: isBpImpl,
          style:    { stroke: color, strokeDasharray: isBpImpl ? '6 3' : undefined },
          markerEnd:    { type: MarkerType.ArrowClosed, color },
          labelStyle:   { fontSize: 10, fill: color },
          labelBgStyle: { fill: '#1F2937' },
        }
      })

      // Dagre 레이아웃 적용 (노드별 실제 너비 반영)
      const GAS_NODE_H = 42
      const g = new dagre.graphlib.Graph()
      g.setDefaultEdgeLabel(() => ({}))
      g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 90, marginx: 40, marginy: 40 })
      rfNodes.forEach(n => {
        const w = (n.data as any)?.nodeWidth ?? GAS_NODE_MIN
        g.setNode(n.id, { width: w, height: GAS_NODE_H })
      })
      rfEdges.forEach(e => { if (e.source !== e.target) g.setEdge(e.source, e.target) })
      dagre.layout(g)
      const laidOut = rfNodes.map(n => {
        const pos = g.node(n.id)
        const w = (n.data as any)?.nodeWidth ?? GAS_NODE_MIN
        return pos ? { ...n, position: { x: pos.x - w / 2, y: pos.y - GAS_NODE_H / 2 } } : n
      })

      setGasNodes(laidOut)
      setGasEdges(rfEdges)
      setSummary(data.summary)
    } catch (e: any) {
      setError(e?.message ?? String(e))
    } finally { setLoading(false) }
  }

  if (!summary && !loading && !error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-500">
        <button onClick={load} className="btn-primary text-sm px-5 py-2">
          {t('gas_gen_btn')}
        </button>
        <p className="text-xs">{t('gas_gen_desc')}</p>
      </div>
    )
  }

  if (loading) return <p className="p-4 text-gray-500 animate-pulse">{t('gas_graph_loading')}</p>
  if (error)   return <p className="p-4 text-red-400 text-sm">Error: {error}</p>

  return (
    <div className="flex flex-col h-full">
      {/* 범례 + 요약 */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-gray-800 shrink-0 flex-wrap">
        {summary && (() => {
          const KEY_MAP: Record<string, { type: string; label: string }> = {
            abilities:    { type: 'ability',    label: 'C++ GA' },
            effects:      { type: 'effect',     label: 'C++ GE' },
            attr_sets:    { type: 'attribute_set', label: 'C++ AS' },
            tags:         { type: 'tag',        label: 'Tag' },
            bp_abilities: { type: 'bp_ability', label: 'BP GA' },
            bp_effects:   { type: 'bp_effect',  label: 'BP GE' },
          }
          return Object.entries(summary).map(([k, v]) => {
            const meta = KEY_MAP[k]
            const color = meta ? GAS_NODE_COLORS[meta.type] : '#374151'
            const label = meta?.label ?? k
            return (
              <span key={k} className="flex items-center gap-1 text-xs text-gray-400">
                <span className="inline-block w-2.5 h-2.5 rounded-sm"
                  style={{ background: color, border: meta?.type.startsWith('bp_') ? '1px dashed rgba(255,255,255,0.4)' : undefined }} />
                {label} <b className="text-white">{v}</b>
              </span>
            )
          })
        })()}
        <button onClick={load} className="ml-auto text-xs text-gray-500 hover:text-gray-300">
          {t('gas_refresh')}
        </button>
      </div>
      <div className="flex-1 min-h-0">
        <ReactFlow
          nodes={gasNodes} edges={gasEdges}
          onNodesChange={onGasNodesChange}
          onEdgesChange={onGasEdgesChange}
          fitView
          attributionPosition="bottom-right"
          style={{ background: '#111827' }}
        >
          <Background color="#374151" gap={20} />
          <Controls />
          <MiniMap nodeColor={n => (n.style?.background as string) ?? '#374151'}
            maskColor="rgba(0,0,0,0.75)" style={{ background: '#1f2937' }} />
        </ReactFlow>
      </div>
    </div>
  )
}

function UE5GasTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [result,    setResult]    = useState('')
  const [loading,   setLoading]   = useState(false)
  const [className, setClassName] = useState('')
  const [view,      setView]      = useState<'text' | 'graph'>('graph')

  async function run() {
    setLoading(true)
    try {
      const res = await engineApi.ue5Gas(scriptsPath, className || undefined)
      setResult(res)
    } catch (e: any) {
      setResult(`Error: ${e?.message ?? e}`)
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 컨트롤 바 */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 shrink-0 flex-wrap">
        {/* 뷰 토글 */}
        <div className="flex gap-1">
          {(['graph', 'text'] as const).map(v => (
            <button key={v} onClick={() => setView(v)}
              className={`text-xs px-3 py-1 rounded border transition-colors
                ${view === v
                  ? 'border-emerald-500 text-emerald-400 bg-emerald-950'
                  : 'border-gray-700 text-gray-400 hover:border-gray-500'}`}>
              {v === 'graph' ? t('gas_view_graph') : t('gas_view_text')}
            </button>
          ))}
        </div>
        {view === 'text' && (
          <>
            <input className="input text-sm w-48" placeholder={t('gas_class_filter_ph')}
              value={className} onChange={e => setClassName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && run()} />
            <button onClick={run} disabled={loading}
              className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
              {loading ? t('analyzing') : t('gas_analyze_btn')}
            </button>
          </>
        )}
        <p className="text-xs text-gray-500">
          {view === 'graph' ? t('gas_graph_flow_desc') : t('gas_text_desc')}
        </p>
      </div>
      {/* 콘텐츠 */}
      <div className="flex-1 overflow-hidden">
        {view === 'graph'
          ? <GasGraph scriptsPath={scriptsPath} />
          : (
            <div className="flex-1 overflow-y-auto h-full border-0 p-4">
              <MdResult text={result} loading={loading} />
            </div>
          )
        }
      </div>
    </div>
  )
}

// ── UE5 Animation 탭 (ABP + Montage) ─────────────────────────
function UE5AnimationTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [result,      setResult]      = useState('')
  const [loading,     setLoading]     = useState(false)
  const [assetType,   setAssetType]   = useState<'all'|'abp'|'montage'>('all')
  const [detailLevel, setDetailLevel] = useState<'summary'|'full'>('summary')

  async function run() {
    setLoading(true)
    try {
      const res = await engineApi.ue5Animation(scriptsPath, assetType, detailLevel)
      setResult(res)
    } catch (e: any) {
      setResult(`Error: ${e?.message ?? e}`)
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-3 overflow-hidden">
      <div className="flex items-center gap-3 shrink-0 flex-wrap">
        {/* 에셋 타입 */}
        <div className="flex gap-1">
          {(['all','abp','montage'] as const).map(v => (
            <button key={v} onClick={() => setAssetType(v)}
              className={`text-xs px-3 py-1 rounded border transition-colors
                ${assetType === v
                  ? 'border-emerald-500 text-emerald-400 bg-emerald-950'
                  : 'border-gray-700 text-gray-400 hover:border-gray-500'}`}>
              {v === 'all' ? t('anim_all') : v === 'abp' ? 'ABP' : 'Montage'}
            </button>
          ))}
        </div>
        {/* 디테일 레벨 */}
        <div className="flex gap-1">
          {(['summary','full'] as const).map(d => (
            <button key={d} onClick={() => setDetailLevel(d)}
              className={`text-xs px-3 py-1 rounded border transition-colors
                ${detailLevel === d
                  ? 'border-blue-500 text-blue-400 bg-blue-950'
                  : 'border-gray-700 text-gray-400 hover:border-gray-500'}`}>
              {d === 'summary' ? t('anim_summary') : t('anim_full')}
            </button>
          ))}
        </div>
        <button onClick={run} disabled={loading}
          className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
          {loading ? t('analyzing') : t('anim_btn')}
        </button>
        <p className="text-xs text-gray-500">{t('anim_desc')}</p>
      </div>
      <div className="flex-1 overflow-y-auto border border-gray-800 rounded bg-gray-900/50 p-4">
        <MdResult text={result} loading={loading} />
      </div>
    </div>
  )
}

// ── UE5 AI (BT + StateTree) 탭 ───────────────────────────────
function UE5AITab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [btResult,  setBtResult]  = useState('')
  const [stResult,  setStResult]  = useState('')
  const [loadingBt, setLoadingBt] = useState(false)
  const [loadingSt, setLoadingSt] = useState(false)
  const [activeAi,  setActiveAi]  = useState<'bt'|'st'>('bt')

  async function runBT() {
    setLoadingBt(true)
    try {
      const res = await engineApi.ue5BehaviorTree(scriptsPath)
      setBtResult(res)
    } catch (e: any) { setBtResult(`Error: ${e?.message ?? e}`) }
    finally { setLoadingBt(false) }
  }

  async function runST() {
    setLoadingSt(true)
    try {
      const res = await engineApi.ue5StateTree(scriptsPath)
      setStResult(res)
    } catch (e: any) { setStResult(`Error: ${e?.message ?? e}`) }
    finally { setLoadingSt(false) }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-3 overflow-hidden">
      {/* Sub-tabs */}
      <div className="flex items-center gap-3 shrink-0 flex-wrap">
        <div className="flex gap-1">
          <button onClick={() => setActiveAi('bt')}
            className={`text-xs px-3 py-1 rounded border transition-colors
              ${activeAi==='bt' ? 'border-orange-500 text-orange-400 bg-orange-950' : 'border-gray-700 text-gray-400 hover:border-gray-500'}`}>
            {t('ai_bt_tab')}
          </button>
          <button onClick={() => setActiveAi('st')}
            className={`text-xs px-3 py-1 rounded border transition-colors
              ${activeAi==='st' ? 'border-purple-500 text-purple-400 bg-purple-950' : 'border-gray-700 text-gray-400 hover:border-gray-500'}`}>
            {t('ai_st_tab')}
          </button>
        </div>
        {activeAi === 'bt' ? (
          <button onClick={runBT} disabled={loadingBt}
            className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
            {loadingBt ? t('analyzing') : t('ai_bt_btn')}
          </button>
        ) : (
          <button onClick={runST} disabled={loadingSt}
            className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
            {loadingSt ? t('analyzing') : t('ai_st_btn')}
          </button>
        )}
        <p className="text-xs text-gray-500">
          {activeAi === 'bt' ? t('ai_bt_desc') : t('ai_st_desc')}
        </p>
      </div>
      <div className="flex-1 overflow-y-auto border border-gray-800 rounded bg-gray-900/50 p-4">
        {activeAi === 'bt'
          ? <MdResult text={btResult}  loading={loadingBt} />
          : <MdResult text={stResult}  loading={loadingSt} />}
      </div>
    </div>
  )
}

// ── UE5 Blueprint ↔ C++ 매핑 탭 ─────────────────────────────
function UE5BpMappingTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [result,    setResult]    = useState('')
  const [loading,   setLoading]   = useState(false)
  const [cppClass,  setCppClass]  = useState('')
  const [total,     setTotal]     = useState<number | undefined>()

  async function run() {
    setLoading(true); setResult(''); setTotal(undefined)
    try {
      const res = await ue5Api.getBlueprintMapping(scriptsPath, cppClass || undefined)
      setResult(res.result)
      setTotal(res.total)
    } catch (e: any) {
      setResult(`Error: ${e?.response?.data?.detail ?? e?.message ?? e}`)
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-3 overflow-hidden">
      <div className="flex items-center gap-3 shrink-0 flex-wrap">
        <input
          className="input text-sm w-64"
          placeholder={t('bp_map_input_ph')}
          value={cppClass}
          onChange={e => setCppClass(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()}
        />
        <button onClick={run} disabled={loading}
          className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
          {loading ? t('analyzing') : t('bp_map_btn')}
        </button>
        {total !== undefined && !loading && (
          <span className="text-xs text-blue-400">
            Blueprint {total}{t('count_unit')} {t('bp_found_label')}
          </span>
        )}
        <p className="text-xs text-gray-500">{t('bp_map_desc')}</p>
      </div>
      <div className="flex-1 overflow-y-auto border border-gray-800 rounded bg-gray-900/50 p-4">
        <MdResult text={result} loading={loading} />
      </div>
    </div>
  )
}

// ── 🧪 테스트 범위 탭 ─────────────────────────────────────────
function TestScopeTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [className, setClassName] = useState('')
  const [depth,     setDepth]     = useState(3)
  const [loading,   setLoading]   = useState(false)
  const [result,    setResult]    = useState<{ target_class: string; affected_count: number; test_file_count: number; test_files: TestScopeFile[] } | null>(null)
  const [error,     setError]     = useState('')

  async function run() {
    if (!className.trim()) return
    setLoading(true); setResult(null); setError('')
    try {
      const res = await analysisApi.testScope(scriptsPath, className.trim(), depth)
      setResult(res)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? String(e))
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-3 overflow-hidden">
      <div className="flex items-center gap-3 shrink-0 flex-wrap">
        <input
          className="input text-sm w-64"
          placeholder={t('test_class_input_ph')}
          value={className}
          onChange={e => setClassName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()}
        />
        <select
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-300"
          value={depth}
          onChange={e => setDepth(Number(e.target.value))}
        >
          {[1,2,3,4,5].map(d => <option key={d} value={d}>depth {d}</option>)}
        </select>
        <button onClick={run} disabled={loading || !className.trim()}
          className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
          {loading ? t('analyzing') : t('test_run_btn')}
        </button>
        <p className="text-xs text-gray-500">{t('test_desc')}</p>
      </div>
      <div className="flex-1 overflow-y-auto border border-gray-800 rounded bg-gray-900/50 p-4">
        {loading && <p className="text-gray-400 animate-pulse">{t('analyzing')}</p>}
        {error   && <p className="text-red-400 text-sm">{error}</p>}
        {result  && !loading && (
          <div className="space-y-4">
            <div className="flex gap-4 text-sm">
              <span className="text-gray-400">{t('test_target_label')} <span className="text-white font-medium">{result.target_class}</span></span>
              <span className="text-gray-400">{t('test_affected_label')} <span className="text-yellow-400 font-medium">{result.affected_count}{t('count_unit')}</span></span>
              <span className="text-gray-400">{t('test_files_count')} <span className="text-green-400 font-medium">{result.test_file_count}{t('count_unit')}</span></span>
            </div>
            {result.test_files.length === 0 ? (
              <p className="text-gray-500 text-sm">{t('test_no_match')}</p>
            ) : (
              <div className="space-y-1">
                {result.test_files.map((f, i) => (
                  <div key={i} className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-gray-800/50 group">
                    <span className="text-green-400 text-xs font-mono shrink-0">✓</span>
                    <span
                      className="text-xs text-gray-300 font-mono flex-1 truncate cursor-pointer hover:text-white"
                      title={f.path}
                      onClick={() => navigator.clipboard.writeText(f.path)}
                    >{f.path}</span>
                    {f.matched_class && (
                      <span className="text-xs text-indigo-400 shrink-0">{f.matched_class}</span>
                    )}
                    <span className="text-xs text-gray-600 shrink-0">{f.engine}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {!loading && !error && !result && (
          <p className="text-gray-600 text-sm">{t('test_run_hint')}</p>
        )}
      </div>
    </div>
  )
}

// ── 🏗️ 아키텍처 어드바이저 탭 ─────────────────────────────────
function AdviseTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [focusClass, setFocusClass] = useState('')
  const [loading,    setLoading]    = useState(false)
  const [report,     setReport]     = useState('')

  async function run() {
    setLoading(true); setReport('')
    try {
      const res = await analysisApi.advise(scriptsPath, focusClass || undefined)
      setReport(res.report)
    } catch (e: any) {
      setReport(`Error: ${e?.response?.data?.detail ?? e?.message ?? e}`)
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-3 overflow-hidden">
      <div className="flex items-center gap-3 shrink-0 flex-wrap">
        <input
          className="input text-sm w-64"
          placeholder={t('advise_focus_ph')}
          value={focusClass}
          onChange={e => setFocusClass(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()}
        />
        <button onClick={run} disabled={loading}
          className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
          {loading ? t('advise_diagnosing') : t('advise_btn')}
        </button>
        <p className="text-xs text-gray-500">{t('advise_desc')}</p>
      </div>
      <div className="flex-1 overflow-y-auto border border-gray-800 rounded bg-gray-900/50 p-4">
        <MdResult text={report} loading={loading} />
      </div>
    </div>
  )
}

// ── 📋 Lint Fix 탭 ────────────────────────────────────────────
function LintFixTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [loading, setLoading] = useState(false)
  const [total,   setTotal]   = useState<number | null>(null)
  const [fixable, setFixable] = useState<number | null>(null)
  const [issues,  setIssues]  = useState<LintFixIssue[]>([])
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [error,    setError]    = useState('')

  async function run() {
    setLoading(true); setIssues([]); setTotal(null); setFixable(null); setError('')
    try {
      const res = await analysisApi.lintFix(scriptsPath)
      setTotal(res.total); setFixable(res.fixable); setIssues(res.results)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? String(e))
    } finally { setLoading(false) }
  }

  function toggleExpand(i: number) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(i) ? next.delete(i) : next.add(i)
      return next
    })
  }

  const severityColor = (s: string) =>
    s === 'Error' ? 'text-red-400' : s === 'Warning' ? 'text-yellow-400' : 'text-blue-400'

  return (
    <div className="flex flex-col h-full p-4 gap-3 overflow-hidden">
      <div className="flex items-center gap-3 shrink-0 flex-wrap">
        <button onClick={run} disabled={loading}
          className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
          {loading ? t('lint_scanning') : t('lint_fix_scan_btn')}
        </button>
        {total !== null && !loading && (
          <div className="flex gap-3 text-sm">
            <span className="text-gray-400">{t('lint_fix_total_lbl')} <span className="text-white font-medium">{total}{t('count_unit')}</span></span>
            <span className="text-gray-400">{t('lint_fix_fixable_lbl')} <span className="text-green-400 font-medium">{fixable}{t('count_unit')}</span></span>
          </div>
        )}
        <p className="text-xs text-gray-500">{t('lint_fix_desc')}</p>
      </div>
      <div className="flex-1 overflow-y-auto border border-gray-800 rounded bg-gray-900/50 p-4">
        {loading && <p className="text-gray-400 animate-pulse">{t('lint_scanning')}</p>}
        {error   && <p className="text-red-400 text-sm">{error}</p>}
        {!loading && issues.length === 0 && total !== null && (
          <p className="text-gray-500 text-sm">{t('lint_fix_none_found')}</p>
        )}
        {!loading && total === null && !error && (
          <p className="text-gray-600 text-sm">{t('lint_fix_run_hint')}</p>
        )}
        <div className="space-y-2">
          {issues.map((issue, i) => (
            <div key={i} className="border border-gray-700 rounded overflow-hidden">
              <button
                onClick={() => toggleExpand(i)}
                className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-800/50 transition-colors"
              >
                <span className={`text-xs font-bold shrink-0 ${severityColor(issue.severity)}`}>[{issue.severity}]</span>
                <span className="text-xs text-purple-400 font-mono shrink-0">{issue.rule_id}</span>
                <span className="text-sm text-gray-300 flex-1 truncate">
                  {issue.class_name}{issue.method_name ? `.${issue.method_name}` : ''}
                </span>
                <span className="text-xs text-gray-500 shrink-0">{expanded.has(i) ? '▲' : '▼'}</span>
              </button>
              {expanded.has(i) && (
                <div className="px-3 pb-3 space-y-2 border-t border-gray-700">
                  <p className="text-xs text-gray-400 pt-2">{issue.message}</p>
                  {issue.file_path && (
                    <p className="text-xs text-gray-600 font-mono truncate">{issue.file_path}</p>
                  )}
                  <div className="rounded bg-gray-950 border border-gray-700 overflow-x-auto">
                    <pre className="text-xs text-green-300 p-3 whitespace-pre-wrap">{issue.fix_suggestion}</pre>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── 📊 Diff 요약 탭 ───────────────────────────────────────────
function DiffSummaryTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [commit,  setCommit]  = useState('HEAD~1')
  const [loading, setLoading] = useState(false)
  const [report,  setReport]  = useState('')

  async function run() {
    setLoading(true); setReport('')
    try {
      const res = await analysisApi.diffSummary(scriptsPath, commit || undefined)
      setReport(res.report)
    } catch (e: any) {
      setReport(`Error: ${e?.response?.data?.detail ?? e?.message ?? e}`)
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-3 overflow-hidden">
      <div className="flex items-center gap-3 shrink-0 flex-wrap">
        <input
          className="input text-sm w-48"
          placeholder={t('diff_commit_ph')}
          value={commit}
          onChange={e => setCommit(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()}
        />
        <button onClick={run} disabled={loading}
          className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
          {loading ? t('analyzing') : t('diff_btn')}
        </button>
        <p className="text-xs text-gray-500">{t('diff_desc')}</p>
      </div>
      <div className="flex-1 overflow-y-auto border border-gray-800 rounded bg-gray-900/50 p-4">
        <MdResult text={report} loading={loading} />
      </div>
    </div>
  )
}

// ── 🪓 Axmol Events 탭 ───────────────────────────────────────
function AxmolEventsTab({ scriptsPath }: { scriptsPath: string }) {
  const { t } = useApp()
  const [methodFilter, setMethodFilter] = useState('')
  const [loading,      setLoading]      = useState(false)
  const [result,       setResult]       = useState('')

  async function run() {
    setLoading(true); setResult('')
    try {
      const res = await engineAnalysisApi.axmolEvents(scriptsPath, methodFilter || undefined)
      setResult(res.result)
    } catch (e: any) {
      setResult(`Error: ${e?.response?.data?.detail ?? e?.message ?? e}`)
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-3 overflow-hidden">
      <div className="flex items-center gap-3 shrink-0 flex-wrap">
        <input
          className="input text-sm w-64"
          placeholder={t('axmol_filter_ph')}
          value={methodFilter}
          onChange={e => setMethodFilter(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()}
        />
        <button onClick={run} disabled={loading}
          className="btn-primary text-sm px-4 py-1.5 disabled:opacity-50">
          {loading ? t('analyzing') : t('axmol_analyze_btn')}
        </button>
        <p className="text-xs text-gray-500">{t('axmol_desc')}</p>
      </div>
      <div className="flex-1 overflow-y-auto border border-gray-800 rounded bg-gray-900/50 p-4">
        <MdResult text={result} loading={loading} />
      </div>
    </div>
  )
}

// ── 메인 ─────────────────────────────────────────────────────
type TabId = 'coupling' | 'inheritance' | 'prefabs' | 'blueprints' | 'deadcode' | 'impact'
           | 'unity_events' | 'unity_animator' | 'ue5_gas' | 'ue5_animation' | 'ue5_ai' | 'ue5_bp_mapping'
           | 'test_scope' | 'advise' | 'lint_fix' | 'diff_summary' | 'axmol_events'

// 엔진 탭 드롭다운 버튼 컴포넌트
function EngineTabDropdown({
  label,
  tabs,
  activeTab,
  onSelect,
}: {
  label: string
  tabs: [TabId, string][]
  activeTab: TabId
  onSelect: (id: TabId) => void
}) {
  const [open, setOpen] = useState(false)
  const isActive = tabs.some(([id]) => id === activeTab)
  const activeLabel = tabs.find(([id]) => id === activeTab)?.[1]

  return (
    <div className="relative shrink-0">
      <button
        onClick={() => setOpen(v => !v)}
        className={`flex items-center gap-1.5 px-3 py-2.5 text-sm transition-colors whitespace-nowrap
          ${isActive ? 'tab-active' : 'tab-inactive'}`}
      >
        {isActive ? activeLabel : label}
        <span className="text-xs opacity-60">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <>
          {/* 바깥 클릭 닫기 */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-full mt-0 z-20 min-w-44
                          bg-gray-900 border border-t-0 border-gray-700 rounded-b shadow-xl">
            {tabs.map(([id, tabLabel]) => (
              <button
                key={id}
                onClick={() => { onSelect(id); setOpen(false) }}
                className={`w-full text-left text-sm px-4 py-2 whitespace-nowrap transition-colors
                  ${activeTab === id
                    ? 'bg-indigo-900 text-indigo-200'
                    : 'text-gray-300 hover:bg-gray-800'}`}
              >
                {tabLabel}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default function DependencyView() {
  const { scriptsPath, projectInfo, t } = useApp()
  const [activeTab, setActiveTab]    = useState<TabId>('coupling')

  const isAxmol  = !!(projectInfo?.engine?.startsWith('Axmol'))
  const isUnity  = projectInfo?.kind === 'UNITY'
  const isUnreal = projectInfo?.kind === 'UNREAL'
  const isCpp    = projectInfo?.kind === 'CPP' && !isAxmol

  if (!scriptsPath) return (
    <div className="flex items-center justify-center h-full text-gray-500">
      {t('dep_no_path')}
    </div>
  )

  // 공통 탭 (항상 표시)
  const commonTabs: [TabId, string][] = [
    ['coupling',    t('dep_coupling')],
    ['inheritance', t('dep_inheritance')],
    ['deadcode',    t('dep_deadcode')],
    ['impact',      t('dep_impact')],
    ['test_scope',  t('dep_test_scope')],
    ['advise',      t('dep_advise')],
    ['lint_fix',    t('dep_lint_fix')],
    ['diff_summary',t('dep_diff_summary')],
  ]

  // 엔진별 탭 (드롭다운으로 묶음)
  const unityTabs: [TabId, string][] = [
    ['prefabs',        t('dep_prefabs')],
    ['unity_events',   t('dep_unity_events')],
    ['unity_animator', t('dep_unity_anim')],
  ]

  const ue5Tabs: [TabId, string][] = [
    ['blueprints',     t('dep_blueprints')],
    ['ue5_gas',        t('dep_ue5_gas')],
    ['ue5_animation',  t('dep_ue5_anim')],
    ['ue5_ai',         t('dep_ue5_ai')],
    ['ue5_bp_mapping', t('dep_ue5_bp_map')],
  ]

  const axmolTabs: [TabId, string][] = [
    ['axmol_events', t('dep_axmol_events')],
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 탭바: 공통탭(스크롤) + 엔진 드롭다운(고정) 2단 구조 */}
      <div className="flex border-b border-gray-800 bg-gray-950 shrink-0 items-stretch">
        {/* 공통 탭 영역 — 가로 스크롤, overflow:visible 유지해서 드롭다운 clip 방지 */}
        <div className="flex flex-nowrap overflow-x-auto flex-1 items-end px-2"
          style={{ scrollbarWidth: 'thin', scrollbarColor: '#374151 transparent' }}>
          {commonTabs.map(([id, label]) => (
            <button key={id} onClick={() => setActiveTab(id)}
              className={`px-3 py-2.5 text-sm transition-colors whitespace-nowrap shrink-0
                ${activeTab === id ? 'tab-active' : 'tab-inactive'}`}>
              {label}
            </button>
          ))}
        </div>

        {/* 엔진 드롭다운 — 오른쪽 고정, overflow:visible 보장 */}
        <div className="flex items-end shrink-0 px-2 border-l border-gray-800">
          {isUnity && (
            <EngineTabDropdown
              label="🎮 Unity ▾"
              tabs={unityTabs}
              activeTab={activeTab}
              onSelect={setActiveTab}
            />
          )}
          {isUnreal && (
            <EngineTabDropdown
              label="⚙️ UE5 ▾"
              tabs={ue5Tabs}
              activeTab={activeTab}
              onSelect={setActiveTab}
            />
          )}
          {isAxmol && (
            <EngineTabDropdown
              label="🪓 Axmol ▾"
              tabs={axmolTabs}
              activeTab={activeTab}
              onSelect={setActiveTab}
            />
          )}
          {/* 엔진 없으면 빈 공간 숨김 */}
          {!isUnity && !isUnreal && !isAxmol && null}
        </div>
      </div>

      {/* 탭 콘텐츠 */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'coupling'       && <CouplingTab      scriptsPath={scriptsPath}/>}
        {activeTab === 'inheritance'    && (
          <InheritanceTab scriptsPath={scriptsPath} isUnreal={isUnreal}/>
        )}
        {activeTab === 'deadcode'       && <DeadCodeTab      scriptsPath={scriptsPath} isUnity={isUnity}/>}
        {activeTab === 'impact'         && <ImpactTab        scriptsPath={scriptsPath}/>}
        {activeTab === 'test_scope'     && <TestScopeTab     scriptsPath={scriptsPath}/>}
        {activeTab === 'advise'         && <AdviseTab        scriptsPath={scriptsPath}/>}
        {activeTab === 'lint_fix'       && <LintFixTab       scriptsPath={scriptsPath}/>}
        {activeTab === 'diff_summary'   && <DiffSummaryTab   scriptsPath={scriptsPath}/>}
        {activeTab === 'prefabs'        && <PrefabRefsTab    scriptsPath={scriptsPath}/>}
        {activeTab === 'blueprints'     && <BlueprintRefsTab scriptsPath={scriptsPath}/>}
        {activeTab === 'unity_events'   && <UnityEventsTab   scriptsPath={scriptsPath}/>}
        {activeTab === 'unity_animator' && <UnityAnimatorTab scriptsPath={scriptsPath}/>}
        {activeTab === 'ue5_gas'        && <UE5GasTab        scriptsPath={scriptsPath}/>}
        {activeTab === 'ue5_animation'  && <UE5AnimationTab  scriptsPath={scriptsPath}/>}
        {activeTab === 'ue5_ai'         && <UE5AITab         scriptsPath={scriptsPath}/>}
        {activeTab === 'ue5_bp_mapping' && <UE5BpMappingTab  scriptsPath={scriptsPath}/>}
        {activeTab === 'axmol_events'   && <AxmolEventsTab   scriptsPath={scriptsPath}/>}
      </div>
    </div>
  )
}
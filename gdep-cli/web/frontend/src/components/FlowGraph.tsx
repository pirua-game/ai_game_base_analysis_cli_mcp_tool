import { useCallback, useEffect, useRef, useState } from 'react'
import dagre from '@dagrejs/dagre'
import {
  ReactFlow, Background, Controls, MiniMap,
  useNodesState, useEdgesState,
  type Node, type Edge, MarkerType, Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useApp } from '../store'
// t() is accessed via useApp()
import { flowApi, llmApi, type FlowNode, type FlowEdge } from '../api/client'

const COLORS = {
  entry:    '#1D9E75',
  async:    '#378ADD',
  dispatch: '#BA7517',
  leaf:     '#5F5E5A',
  default:  '#374151',
  selected: '#78350f',
  selectedBorder: '#f59e0b',
  blueprint:       '#1E3A5F',  // BP 노드 배경 (진한 파랑)
  blueprintBorder: '#3B82F6',  // BP 노드 테두리 (밝은 파랑)
}

function nodeColor(n: FlowNode) {
  if ((n as any).isBlueprintNode) return COLORS.blueprint
  if (n.isEntry)    return COLORS.entry
  if (n.isDispatch) return COLORS.dispatch
  if (n.isLeaf)     return COLORS.leaf
  if (n.isAsync)    return COLORS.async
  return COLORS.default
}

function edgeColor(e: FlowEdge) {
  if (e.context === 'blueprint') return COLORS.blueprintBorder
  if (e.context === 'lock')   return '#E24B4A'
  if (e.context === 'thread') return '#534AB7'
  if (e.context === 'lambda') return '#7F77DD'
  if (e.isDynamic)            return '#BA7517'
  return '#5DCAA5'
}

// ── 노드 너비 동적 계산 ──────────────────────────────────────
const NODE_H    = 44
const CHAR_W    = 7.5   // 13px 폰트 기준 평균 문자 너비 (px)
const NODE_PAD  = 32    // 좌우 padding 합계 (14px × 2 + 여유)
const NODE_MIN  = 110
const NODE_MAX  = 320

function calcNodeWidth(label: string): number {
  return Math.min(NODE_MAX, Math.max(NODE_MIN, Math.ceil(label.length * CHAR_W) + NODE_PAD))
}

function makeNodes(fnodes: FlowNode[], selId: string | null): Node[] {
  return fnodes.map((n) => {
    const isSel  = n.id === selId
    const label  = `${(n as any).isBlueprintNode ? '[BP] ' : ''}${n.label ?? n.method}${n.isAsync ? ' ⏱' : ''}`
    const nodeW  = calcNodeWidth(label)
    return {
      id:   n.id,
      data: { label, nodeWidth: nodeW },
      position: { x: 0, y: 0 },   // dagre가 계산 후 덮어씀
      style: {
        background:   isSel ? COLORS.selected : nodeColor(n),
        color:        '#fff',
        border:       isSel
          ? `3px solid ${COLORS.selectedBorder}`
          : (n as any).isBlueprintNode ? `2px solid ${COLORS.blueprintBorder}`
          : n.isEntry ? '2px solid #34D399' : '1px solid #4B5563',
        borderRadius: 8,
        fontSize:     13,
        fontWeight:   isSel || n.isEntry ? 700 : 400,
        padding:      '6px 14px',
        width:        nodeW,
        boxShadow:    isSel ? '0 0 18px rgba(245,158,11,0.65)'
          : (n as any).isBlueprintNode ? '0 0 10px rgba(59,130,246,0.4)' : undefined,
        cursor:       'pointer',
        transition:   'background 0.15s, border 0.15s, box-shadow 0.15s',
      },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    }
  })
}

// ── Dagre 자동 레이아웃 ──────────────────────────────────────
function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({
    rankdir:  'TB',   // Top → Bottom (진입점 최상단)
    nodesep:  50,     // 같은 rank 내 노드 간 수평 간격
    ranksep:  80,     // rank 간 수직 간격
    marginx:  40,
    marginy:  40,
  })

  nodes.forEach(n => {
    const w = (n.data as any)?.nodeWidth ?? NODE_MIN
    g.setNode(n.id, { width: w, height: NODE_H })
  })
  edges.forEach(e => {
    // self-edge 는 레이아웃에서 제외 (dagre가 처리 못함)
    if (e.source !== e.target) g.setEdge(e.source, e.target)
  })

  dagre.layout(g)

  return nodes.map(n => {
    const pos = g.node(n.id)
    if (!pos) return n
    const w = (n.data as any)?.nodeWidth ?? NODE_MIN
    return {
      ...n,
      position: {
        x: pos.x - w / 2,
        y: pos.y - NODE_H / 2,
      },
    }
  })
}

function makeEdges(fedges: FlowEdge[]): Edge[] {
  const seen = new Set<string>()
  return fedges.flatMap(e => {
    const key = `${e.from}→${e.to}`
    if (seen.has(key)) return []
    seen.add(key)
    const color = edgeColor(e)
    const isBpEdge = e.context === 'blueprint'
    return [{
      id: key, source: e.from, target: e.to,
      label:        e.context ?? (e.isDynamic ? 'dispatch' : undefined),
      animated:     !!e.isDynamic,
      style:        { stroke: color, strokeDasharray: isBpEdge ? '6 3' : undefined },
      markerEnd:    { type: MarkerType.ArrowClosed, color },
      labelStyle:   { fontSize: 11, fill: isBpEdge ? '#3B82F6' : '#9CA3AF' },
      labelBgStyle: { fill: '#1F2937' },
    }]
  })
}

export default function FlowGraph() {
  const {
    flowData, setFlowData, breadcrumb, setBreadcrumb,
    flowHistory, setFlowHistory,
    scriptsPath, depth, focusClasses,
    selectedNode, setSelectedNode, llmConfig, t,
  } = useApp()

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [llmResult,  setLlmResult]  = useState('')
  const [llmLoading, setLlmLoading] = useState(false)
  const [drilling,   setDrilling]   = useState(false)

  // ★ 드래그 여부 추적 — onNodeDragStart/Stop 사용
  const isDragging = useRef(false)

  useEffect(() => {
    if (!flowData) return
    const rawNodes = makeNodes(flowData.nodes, selectedNode)
    const rawEdges = makeEdges(flowData.edges)
    const laidOut  = applyDagreLayout(rawNodes, rawEdges)
    setNodes(laidOut)
    setEdges(rawEdges)
  }, [flowData, selectedNode])

  const onNodeDragStart = useCallback(() => {
    isDragging.current = true
  }, [])

  const onNodeDragStop = useCallback(() => {
    // 약간의 딜레이 후 false 처리 — click 이벤트가 dragStop 직후 발생하기 때문
    setTimeout(() => { isDragging.current = false }, 50)
  }, [])

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    if (isDragging.current) return   // 드래그 중엔 선택 무시
    setSelectedNode(node.id === selectedNode ? null : node.id)
  }, [selectedNode])

  async function doDrilldown() {
    if (!selectedNode || !flowData) return
    const fn = flowData.nodes.find(n => n.id === selectedNode)
    if (!fn || fn.isLeaf || fn.isDispatch) return
    setDrilling(true)
    try {
      const data = await flowApi.analyze(scriptsPath, fn.class, fn.method, depth, focusClasses)

      // ── 스택 추적: entry → 선택 노드 경로를 BFS로 탐색 ──────────
      const entryNode = flowData.nodes.find(n => n.isEntry)
      const path      = _findPath(flowData, entryNode?.id ?? null, selectedNode)

      // 현재 breadcrumb 마지막 항목(= 현재 화면의 entry)을 기준으로 중간 단계 삽입
      // 단, 이미 breadcrumb에 있는 항목은 중복 추가하지 않음
      const existingIds = new Set(breadcrumb.map(b => `${b.cls}.${b.method}`))
      const newSteps = path
        .filter(n => !n.isEntry)                          // entry 자체는 이미 breadcrumb에 있음
        .filter(n => n.id !== selectedNode)               // 마지막(드릴다운 대상)은 아래에서 추가
        .filter(n => !existingIds.has(`${n.class}.${n.method}`))
        .map(n => ({ cls: n.class, method: n.method }))

      // flowHistory에 현재 flowData 저장 후 드릴다운
      const newHistory = [...flowHistory, flowData!]
      setFlowHistory(newHistory)
      setBreadcrumb([...breadcrumb, ...newSteps, { cls: fn.class, method: fn.method }])
      setFlowData(data)
      setSelectedNode(null)
      setLlmResult('')
    } finally { setDrilling(false) }
  }

  /** BFS로 start → target 경로의 FlowNode[] 반환 (start 포함, target 포함) */
  function _findPath(data: typeof flowData, startId: string | null, targetId: string): FlowNode[] {
    if (!data || !startId) return []
    const adj: Record<string, string[]> = {}
    for (const e of data.edges) {
      if (!adj[e.from]) adj[e.from] = []
      adj[e.from].push(e.to)
    }
    const queue: string[][] = [[startId]]
    const visited = new Set<string>()
    while (queue.length) {
      const path = queue.shift()!
      const cur  = path[path.length - 1]
      if (cur === targetId) {
        return path.map(id => data.nodes.find(n => n.id === id)!).filter(Boolean)
      }
      if (visited.has(cur)) continue
      visited.add(cur)
      for (const next of adj[cur] ?? []) queue.push([...path, next])
    }
    return []
  }

  async function doLlmAnalyze() {
    if (!flowData) return
    setLlmLoading(true); setLlmResult('')
    try {
      const res = await llmApi.analyzeFlow(flowData, breadcrumb, llmConfig, flowHistory)
      setLlmResult(res.result)
    } finally { setLlmLoading(false) }
  }

  const selFn    = selectedNode ? flowData?.nodes.find(n => n.id === selectedNode) : null
  const canDrill = selFn && !selFn.isLeaf && !selFn.isDispatch

  if (!flowData) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-500">
        <span className="text-5xl">🔀</span>
        <p className="text-base">{t('no_flow')}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* 상단 바 */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-800 shrink-0 flex-wrap">
        {/* 브레드크럼 */}
        <div className="flex items-center gap-1 text-sm flex-1 min-w-0 overflow-x-auto">
          {breadcrumb.map((b, i) => (
            <span key={i} className="flex items-center gap-1 shrink-0">
              {i > 0 && <span className="text-gray-600">›</span>}
              <button
                className="text-emerald-400 hover:text-emerald-300 hover:underline"
                onClick={async () => {
                  const nb = breadcrumb.slice(0, i + 1)
                  setBreadcrumb(nb)
                  setFlowHistory(flowHistory.slice(0, i))  // i단계 이후 history 제거
                  const last = nb[nb.length - 1]
                  // flowHistory[i-1]이 있으면 재분석 없이 복원 가능
                  const cached = i > 0 ? flowHistory[i - 1] : null
                  const d = cached ?? await flowApi.analyze(scriptsPath, last.cls, last.method, depth, focusClasses)
                  setFlowData(d); setSelectedNode(null); setLlmResult('')
                }}
              >
                {b.cls}.{b.method}
              </button>
            </span>
          ))}
        </div>

        {/* 메트릭 */}
        <div className="flex gap-3 text-sm text-gray-400 shrink-0">
          <span>{t('nodes')} <b className="text-white">{flowData.nodes.length}</b></span>
          <span>{t('edges')} <b className="text-white">{flowData.edges.length}</b></span>
          {flowData.dispatches.length > 0 &&
            <span>{t('dispatches')} <b className="text-yellow-400">{flowData.dispatches.length}</b></span>}
          {(flowData as any).bpBridge && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full
                             bg-blue-950 border border-blue-700 text-blue-300 text-xs">
              🔵 Blueprint bridge
            </span>
          )}
        </div>

        <button onClick={doLlmAnalyze} disabled={llmLoading}
          className="btn-secondary text-sm shrink-0 disabled:opacity-50">
          {llmLoading ? t('llm_analyzing') : t('llm_interpret')}
        </button>
      </div>

      {/* 선택 노드 액션 바 */}
      {selFn ? (
        <div className="flex items-center gap-3 px-4 py-2.5
                        bg-amber-950 border-b border-amber-800 shrink-0">
          <span className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ background: COLORS.selectedBorder, boxShadow: '0 0 6px rgba(245,158,11,0.8)' }} />
          <span className="text-sm text-amber-200 font-mono truncate flex-1">
            {selFn.class}.{selFn.method}
            {selFn.isAsync  && <span className="ml-2 text-blue-400 font-sans">⏱ {t('async_label')}</span>}
            {selFn.isEntry  && <span className="ml-2 text-emerald-400 font-sans">{t('entry_label')}</span>}
            {selFn.isLeaf   && <span className="ml-2 text-gray-500 font-sans">{t('leaf_label')}</span>}
          </span>

          {canDrill ? (
            <button onClick={doDrilldown} disabled={drilling}
              className="shrink-0 flex items-center gap-2 px-3 py-1.5 rounded
                         bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-medium
                         border border-emerald-600 transition-colors disabled:opacity-50">
              {drilling ? t('llm_analyzing') : t('drilldown')}
            </button>
          ) : (
            <span className="text-sm text-gray-500 shrink-0">
              {selFn.isLeaf ? t('leaf_no_drilldown') : t('no_drilldown')}
            </span>
          )}

          <button onClick={() => setSelectedNode(null)}
            className="shrink-0 text-sm text-gray-500 hover:text-gray-300 px-2">
            ✕
          </button>
        </div>
      ) : (
        /* 선택 전 안내 */
        <div className="px-4 py-1.5 border-b border-gray-800 shrink-0">
          <p className="text-xs text-gray-600">{t('drilldown_hint')}</p>
        </div>
      )}

      {/* 그래프 */}
      <div className="flex-1 min-h-0">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick as any}
          onNodeDragStart={onNodeDragStart as any}
          onNodeDragStop={onNodeDragStop as any}
          fitView
          attributionPosition="bottom-right"
          style={{ background: '#111827' }}
        >
          <Background color="#374151" gap={20} />
          <Controls />
          <MiniMap
            nodeColor={n => (n.style?.background as string) ?? '#374151'}
            maskColor="rgba(0,0,0,0.75)"
            style={{ background: '#1f2937' }}
          />
        </ReactFlow>
      </div>

      {/* LLM 결과 */}
      {llmResult && (
        <div className="border-t border-gray-800 p-4 max-h-52 overflow-y-auto shrink-0 bg-gray-950">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-emerald-400">{t('llm_result_title')}</h3>
            <button onClick={() => setLlmResult('')}
              className="text-sm text-gray-500 hover:text-gray-300">{t('close_btn')}</button>
          </div>
          <p className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">{llmResult}</p>
        </div>
      )}

      {/* 범례 */}
      <div className="flex flex-wrap gap-3 px-4 py-1.5 border-t border-gray-800 text-xs text-gray-500 shrink-0">
        {([
          [t('entry_point'), '#1D9E75'],
          ['async',          '#378ADD'],
          ['dispatch',       '#BA7517'],
          [t('leaf_node'),   '#5F5E5A'],
          [t('selected_label'), '#78350f'],
          ['Blueprint',      '#1E3A5F'],
        ] as const).map(([label, color]) => (
          <span key={label} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: color }} />
            {label}
          </span>
        ))}
        <span className="ml-auto text-gray-600">{t('legend_hint')}</span>
      </div>
    </div>
  )
}

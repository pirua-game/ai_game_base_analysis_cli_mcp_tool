import { useState, useEffect, useRef, useCallback } from 'react'
import dagre from '@dagrejs/dagre'
import {
  ReactFlow, Background, Controls,
  useNodesState, useEdgesState,
  type Node, type Edge, MarkerType, Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useApp } from '../store'
import MdResult from './MdResult'
import {
  wikiApi,
  type WikiNode, type WikiSearchResult, type WikiStats,
  type WikiGraphNode, type WikiGraphEdge, type WikiGraphData,
} from '../api/client'

// ── 타입별 색상 / 배지 ─────────────────────────────────────────
const TYPE_COLOR: Record<string, string> = {
  class:        '#1D9E75',
  asset:        '#378ADD',
  system:       '#7C3AED',
  pattern:      '#D97706',
  conversation: '#6B7280',
  unknown:      '#374151',
}

const TYPE_BADGE: Record<string, string> = {
  class:        'bg-emerald-900 text-emerald-300',
  asset:        'bg-blue-900 text-blue-300',
  system:       'bg-purple-900 text-purple-300',
  pattern:      'bg-orange-900 text-orange-300',
  conversation: 'bg-gray-700 text-gray-300',
}

// ── Dagre 레이아웃 ────────────────────────────────────────────
function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 80 })
  nodes.forEach(n => g.setNode(n.id, { width: 160, height: 44 }))
  edges.forEach(e => g.setEdge(e.source, e.target))
  dagre.layout(g)
  return nodes.map(n => {
    const pos = g.node(n.id)
    return { ...n, position: { x: pos.x - 80, y: pos.y - 22 } }
  })
}

// ── ReactFlow 노드/엣지 변환 ──────────────────────────────────
function toRfNodes(graphNodes: WikiGraphNode[], selectedId: string | null): Node[] {
  return graphNodes.map(n => ({
    id: n.id,
    data: { label: n.label },
    position: { x: 0, y: 0 },
    style: {
      background: n.id === selectedId
        ? '#78350f'
        : (TYPE_COLOR[n.type] ?? TYPE_COLOR.unknown),
      color: '#fff',
      border: n.id === selectedId
        ? '2px solid #f59e0b'
        : '1px solid #4B5563',
      borderRadius: 8,
      fontSize: 12,
      padding: '6px 12px',
      width: 160,
      opacity: n.stale ? 0.7 : 1,
      cursor: 'pointer',
    },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  }))
}

function toRfEdges(graphEdges: WikiGraphEdge[]): Edge[] {
  return graphEdges.map((e, i) => ({
    id: `e${i}-${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    label: e.relation,
    style: { stroke: '#5DCAA5' },
    labelStyle: { fill: '#9CA3AF', fontSize: 10 },
    markerEnd: { type: MarkerType.ArrowClosed, color: '#5DCAA5' },
  }))
}

// ── 그래프 서브컴포넌트 ────────────────────────────────────────
function WikiGraph({
  graphData, selectedId, onNodeClick, depth, setDepth, loading, t,
}: {
  graphData: WikiGraphData | null
  selectedId: string | null
  onNodeClick: (id: string) => void
  depth: number
  setDepth: (d: number) => void
  loading: boolean
  t: (k: string) => string
}) {
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<Node>([])
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<Edge>([])

  useEffect(() => {
    if (!graphData) return
    const nodes = toRfNodes(graphData.nodes, selectedId)
    const edges = toRfEdges(graphData.edges)
    if (nodes.length > 0) {
      setRfNodes(applyDagreLayout(nodes, edges))
    } else {
      setRfNodes([])
    }
    setRfEdges(edges)
  }, [graphData, selectedId, setRfNodes, setRfEdges])

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* depth 컨트롤 */}
      <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-gray-800 shrink-0">
        <span className="text-xs text-gray-500">{t('wiki_depth_label')}:</span>
        {[1, 2, 3].map(d => (
          <button
            key={d}
            onClick={() => setDepth(d)}
            className={`w-6 h-6 text-xs rounded transition-colors ${
              depth === d
                ? 'bg-emerald-700 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {d}
          </button>
        ))}
      </div>
      <div className="flex-1 relative">
        {loading ? (
          <div className="flex items-center justify-center h-full text-gray-500 text-sm animate-pulse">
            {t('wiki_loading')}
          </div>
        ) : rfNodes.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-600 text-sm">
            {t('wiki_no_graph')}
          </div>
        ) : (
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={(_, n) => onNodeClick(n.id)}
            fitView
            colorMode="dark"
          >
            <Background />
            <Controls />
          </ReactFlow>
        )}
      </div>
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────
export default function WikiView() {
  const { scriptsPath, t } = useApp()

  // 검색/필터 상태
  const [searchQuery, setSearchQuery]     = useState('')
  const [searchMode, setSearchMode]       = useState<'or' | 'and' | 'phrase'>('or')
  const [typeFilter, setTypeFilter]       = useState('')
  const [relatedToggle, setRelatedToggle] = useState(false)

  // 데이터
  const [nodes, setNodes]                 = useState<WikiNode[]>([])
  const [searchResults, setSearchResults] = useState<WikiSearchResult[] | null>(null)
  const [stats, setStats]                 = useState<WikiStats | null>(null)
  const [selectedNode, setSelectedNode]   = useState<WikiNode | null>(null)
  const [nodeContent, setNodeContent]     = useState('')
  const [graphData, setGraphData]         = useState<WikiGraphData | null>(null)

  // UI 상태
  const [rightTab, setRightTab]   = useState<'detail' | 'graph'>('detail')
  const [graphDepth, setGraphDepth] = useState(1)
  const [listLoading, setListLoading]   = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [graphLoading, setGraphLoading]   = useState(false)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 초기 로드 / 경로·타입필터 변경 시
  useEffect(() => {
    if (!scriptsPath) return
    setListLoading(true)
    setSelectedNode(null)
    setNodeContent('')
    setGraphData(null)
    setSearchResults(null)
    Promise.all([
      wikiApi.stats(scriptsPath),
      wikiApi.list(scriptsPath, typeFilter || undefined),
    ])
      .then(([s, n]) => { setStats(s); setNodes(n) })
      .catch(() => {})
      .finally(() => setListLoading(false))
  }, [scriptsPath, typeFilter])

  // 검색 debounce
  useEffect(() => {
    if (!scriptsPath || !searchQuery.trim()) {
      setSearchResults(null)
      return
    }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      wikiApi
        .search(scriptsPath, searchQuery, searchMode, typeFilter || undefined, relatedToggle)
        .then(r => setSearchResults(r))
        .catch(() => {})
    }, 400)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [scriptsPath, searchQuery, searchMode, typeFilter, relatedToggle])

  // 노드 선택 → detail + graph 병렬 fetch
  const selectNode = useCallback((nodeId: string, depth?: number) => {
    if (!scriptsPath) return
    const d = depth ?? graphDepth
    setDetailLoading(true)
    setGraphLoading(true)
    Promise.all([
      wikiApi.node(scriptsPath, nodeId),
      wikiApi.graph(scriptsPath, nodeId, d),
    ])
      .then(([detail, graph]) => {
        setSelectedNode(detail.node)
        setNodeContent(detail.content)
        setGraphData(graph)
      })
      .catch(() => {})
      .finally(() => { setDetailLoading(false); setGraphLoading(false) })
  }, [scriptsPath, graphDepth])

  // depth 변경 시 그래프만 재로드
  const handleDepthChange = useCallback((d: number) => {
    setGraphDepth(d)
    if (!scriptsPath || !selectedNode) return
    setGraphLoading(true)
    wikiApi.graph(scriptsPath, selectedNode.id, d)
      .then(graph => setGraphData(graph))
      .catch(() => {})
      .finally(() => setGraphLoading(false))
  }, [scriptsPath, selectedNode])

  // 그래프 노드 클릭 → detail 탭으로 이동
  const handleGraphNodeClick = useCallback((nodeId: string) => {
    setRightTab('detail')
    selectNode(nodeId)
  }, [selectNode])

  const displayList = searchResults ? searchResults.map(r => r.node) : nodes

  if (!scriptsPath) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 text-sm">
        {t('wiki_no_path')}
      </div>
    )
  }

  return (
    <div className="flex h-full overflow-hidden">

      {/* ── 좌측 패널 ───────────────────────────────────────── */}
      <div className="w-72 shrink-0 border-r border-gray-800 flex flex-col overflow-hidden">

        {/* Stats Bar */}
        {stats && (
          <div className="px-2 py-1.5 border-b border-gray-800 flex flex-wrap gap-1 items-center">
            {Object.entries(stats.types).map(([type, count]) => (
              <button
                key={type}
                onClick={() => setTypeFilter(typeFilter === type ? '' : type)}
                className={`text-xs px-1.5 py-0.5 rounded transition-colors ${
                  typeFilter === type
                    ? 'ring-1 ring-white/30 opacity-100'
                    : 'opacity-80 hover:opacity-100'
                } ${TYPE_BADGE[type] ?? 'bg-gray-700 text-gray-300'}`}
              >
                {type}:{count}
              </button>
            ))}
            {stats.stale_count > 0 && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-900 text-yellow-300">
                ⚠{stats.stale_count}
              </span>
            )}
            <span className="text-xs text-gray-600 ml-auto">
              {stats.total_edges} {t('wiki_total_edges')}
            </span>
          </div>
        )}

        {/* 검색 박스 */}
        <div className="p-2 border-b border-gray-800 space-y-1.5">
          <input
            className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-emerald-600"
            placeholder={t('wiki_search_ph')}
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
          <div className="flex gap-1">
            {(['or', 'and', 'phrase'] as const).map(m => (
              <button
                key={m}
                onClick={() => setSearchMode(m)}
                className={`flex-1 text-xs py-0.5 rounded transition-colors ${
                  searchMode === m
                    ? 'bg-emerald-700 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {t(`wiki_mode_${m}` as 'wiki_mode_or')}
              </button>
            ))}
          </div>
          <div className="flex gap-1.5 items-center">
            <select
              className="flex-1 bg-gray-900 border border-gray-700 rounded px-1.5 py-1 text-xs text-gray-300 focus:outline-none"
              value={typeFilter}
              onChange={e => setTypeFilter(e.target.value)}
            >
              <option value="">{t('wiki_type_all')}</option>
              {['class', 'asset', 'system', 'pattern', 'conversation'].map(tp => (
                <option key={tp} value={tp}>{tp}</option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer whitespace-nowrap">
              <input
                type="checkbox"
                checked={relatedToggle}
                onChange={e => setRelatedToggle(e.target.checked)}
                className="accent-emerald-500"
              />
              {t('wiki_related_toggle')}
            </label>
          </div>
        </div>

        {/* 노드 목록 */}
        <div className="flex-1 overflow-y-auto">
          {listLoading ? (
            <p className="p-3 text-sm text-gray-500 animate-pulse">{t('wiki_loading')}</p>
          ) : displayList.length === 0 ? (
            <p className="p-3 text-sm text-gray-600">{t('wiki_empty')}</p>
          ) : (
            <>
              {searchResults && (
                <div className="px-2 py-1 text-xs text-gray-500 border-b border-gray-800">
                  {t('wiki_search_results')}: {searchResults.length}
                </div>
              )}
              {displayList.map(node => (
                <button
                  key={node.id}
                  onClick={() => { selectNode(node.id); setRightTab('detail') }}
                  className={`w-full text-left px-2.5 py-2 border-b border-gray-800 hover:bg-gray-800 transition-colors ${
                    selectedNode?.id === node.id ? 'bg-gray-800' : ''
                  }`}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ background: TYPE_COLOR[node.type] ?? TYPE_COLOR.unknown }}
                    />
                    <span className="text-sm text-gray-200 truncate flex-1">{node.title}</span>
                    {node.stale && <span className="text-xs text-yellow-400 shrink-0">⚠</span>}
                  </div>
                  <div className="text-xs text-gray-600 pl-3.5 mt-0.5">
                    {node.updated_at ? node.updated_at.slice(0, 10) : ''}
                  </div>
                </button>
              ))}
            </>
          )}
        </div>
      </div>

      {/* ── 우측 패널 ───────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">

        {/* 탭 헤더 */}
        <div className="flex border-b border-gray-800 shrink-0">
          {(['detail', 'graph'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setRightTab(tab)}
              className={`px-4 py-2.5 text-sm font-medium transition-colors ${
                rightTab === tab
                  ? 'text-emerald-400 border-b-2 border-emerald-400'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {t(tab === 'detail' ? 'wiki_detail_tab' : 'wiki_graph_tab')}
            </button>
          ))}
        </div>

        {/* 탭 콘텐츠 */}
        {rightTab === 'detail' ? (
          <div className="flex-1 overflow-y-auto p-4">
            {!selectedNode ? (
              <p className="text-gray-600 text-sm">{t('wiki_no_select')}</p>
            ) : (
              <div className="space-y-4 max-w-3xl">
                {/* 메타데이터 패널 */}
                <div className="bg-gray-900 rounded-lg p-3 space-y-2.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-xs px-2 py-0.5 rounded font-medium ${
                        TYPE_BADGE[selectedNode.type] ?? 'bg-gray-700 text-gray-300'
                      }`}
                    >
                      {selectedNode.type}
                    </span>
                    <span className="text-base font-semibold text-gray-100">
                      {selectedNode.title}
                    </span>
                    {selectedNode.stale && (
                      <span className="text-xs text-yellow-400 ml-auto">{t('wiki_stale_badge')}</span>
                    )}
                  </div>

                  <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
                    <span className="text-gray-500">{t('wiki_node_id')}</span>
                    <span className="text-gray-400 font-mono truncate">{selectedNode.id}</span>
                    <span className="text-gray-500">{t('wiki_node_updated')}</span>
                    <span className="text-gray-300">{selectedNode.updated_at ? selectedNode.updated_at.slice(0, 10) : '—'}</span>
                    <span className="text-gray-500">{t('wiki_node_created')}</span>
                    <span className="text-gray-300">{selectedNode.created_at ? selectedNode.created_at.slice(0, 10) : '—'}</span>
                    {selectedNode.file_path && (
                      <>
                        <span className="text-gray-500">{t('wiki_node_file')}</span>
                        <span className="text-gray-400 font-mono text-xs truncate">{selectedNode.file_path}</span>
                      </>
                    )}
                  </div>

                  {selectedNode.stale && (
                    <p className="text-xs text-yellow-400 bg-yellow-950/40 border border-yellow-800/50 rounded p-2">
                      {t('wiki_stale_warn')}
                    </p>
                  )}
                </div>

                {/* 마크다운 콘텐츠 */}
                {detailLoading ? (
                  <p className="text-sm text-gray-500 animate-pulse">{t('wiki_loading')}</p>
                ) : (
                  <MdResult text={nodeContent} loading={false} />
                )}
              </div>
            )}
          </div>
        ) : (
          <WikiGraph
            graphData={graphData}
            selectedId={selectedNode?.id ?? null}
            onNodeClick={handleGraphNodeClick}
            depth={graphDepth}
            setDepth={handleDepthChange}
            loading={graphLoading}
            t={t as (k: string) => string}
          />
        )}
      </div>
    </div>
  )
}

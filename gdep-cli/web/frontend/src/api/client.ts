import axios from 'axios'

const BASE = 'http://localhost:8000/api'
const api  = axios.create({ baseURL: BASE })

// ── 타입 ──────────────────────────────────────────────────────

export interface ProjectInfo {
  kind: string; engine: string; language: string
  display: string; name: string; root: string; source_dirs: string[]
}
export interface ClassField  { name: string; type: string; access: string }
export interface ClassMethod { name: string; ret: string; params: string[]; isAsync: boolean; access: string }
export interface ClassInfo   { kind: string; bases: string[]; fields: ClassField[]; methods: ClassMethod[] }
export interface ClassMap    { classes: Record<string, ClassInfo>; count: number; kind: string }
export interface CouplingItem{ rank: number; name: string; score: number }
export interface DeadNode    { name: string; ns: string; file: string }
export interface ScanResult  { coupling: CouplingItem[]; cycles: string[]; deadNodes?: DeadNode[] }

export interface ImpactNode  { name: string; file: string; children: ImpactNode[] }
export interface ImpactResult{ stdout: string; tree: ImpactNode | null }

export interface LintIssue {
  rule_id: string; severity: string; message: string
  class_name: string; method_name: string; file_path: string; suggestion: string
}
export interface LintResult  { issues: LintIssue[]; count: number }
export interface FlowNode {
  id: string; class: string; method: string; label: string
  isEntry?: boolean; isLeaf?: boolean; isAsync?: boolean; isDispatch?: boolean
}
export interface FlowEdge { from: string; to: string; context?: string; isDynamic?: boolean; condition?: string }
export interface FlowData {
  entry: string; entryClass: string; depth: number
  nodes: FlowNode[]; edges: FlowEdge[]
  dispatches: { from: string; handler: string }[]
}
export interface PrefabRef { guid: string; prefabs: string[]; scenes: string[]; total: number }
export interface AgentEvent {
  type: 'tool_call'|'tool_result'|'answer'|'error'
  tool?: string; args?: Record<string, unknown>
  result?: string; content?: string; message?: string; call_num?: number
}
export interface LLMConfig {
  provider: string; model: string; api_key?: string; base_url?: string
}

// ── API 함수 ──────────────────────────────────────────────────

// Phase 1-5: describe 구조화 응답 타입
export interface DescribeResult {
  class_name:        string
  kind:              string
  file_path:         string
  inheritance_chain: string[]
  also_implements:   string[]
  stdout:            string   // 하위호환용 raw text
}

// Phase 1-2: explain_method_logic 타입
export interface ControlFlowItem { type: string; text: string }
export interface ExplainMethodResult {
  raw:         string
  items:       ControlFlowItem[]
  source_file: string
  confidence:  string
}

// Phase 1-3: project context 타입
export interface ProjectContextResult {
  context:        string
  has_agents_md:  boolean
  agents_md_path: string
}

// Phase 1-4: init 타입
export interface InitResult {
  success:        boolean
  agents_md_path: string
  message:        string
}

export interface BrowseResult { parent: string; dirs: string[]; is_root: boolean }

export const projectApi = {
  browse:     (path = '') =>
    api.get<BrowseResult>('/project/browse', { params: { path } }).then(r => r.data),
  detect:     (path: string) =>
    api.get<ProjectInfo>('/project/detect', { params: { path } }).then(r => r.data),
  scan:       (path: string, top = 20, circular = true, dead_code = false, deep = false, include_refs = false) =>
    api.post<ScanResult>('/project/scan', { path, top, circular, dead_code, deep, include_refs }).then(r => r.data),
  describe:   (path: string, class_name: string) =>
    api.post<DescribeResult>('/project/describe', { path, class_name }).then(r => r.data),
  readSource: (path: string, class_name: string, max_chars = 8000, method_name?: string) =>
    api.post<{ content: string }>('/project/read_source', { path, class_name, max_chars, method_name: method_name ?? null }).then(r => r.data),
  impact:     (path: string, target_class: string, depth = 3) =>
    api.post<ImpactResult>('/project/impact', { path, target_class, depth }).then(r => r.data),
  lint:       (path: string) =>
    api.post<LintResult>('/project/lint', { path }).then(r => r.data),
  explainMethodLogic: (path: string, class_name: string, method_name: string, include_source = false) =>
    api.post<ExplainMethodResult>('/project/explain-method-logic', { path, class_name, method_name, include_source }).then(r => r.data),
  getContext: (path: string) =>
    api.get<ProjectContextResult>('/project/context', { params: { path } }).then(r => r.data),
  init:       (path: string, force = false) =>
    api.post<InitResult>('/project/init', { path, force }).then(r => r.data),
}

export const classesApi = {
  list: (path: string) =>
    api.get<ClassMap>('/classes/list', { params: { path } }).then(r => r.data),
}

export const flowApi = {
  analyze: (path: string, class_name: string, method_name: string,
            depth = 3, focus_classes: string[] = []) =>
    api.post<FlowData>('/flow/analyze',
      { path, class_name, method_name, depth, focus_classes }).then(r => r.data),
}

export const unityApi = {
  getRefs: (path: string) =>
    api.get<{ refs: Record<string, PrefabRef>; total_classes: number; used_classes: number }>
      ('/unity/refs', { params: { path } }).then(r => r.data),
  getClassRefs: (path: string, class_name: string) =>
    api.get<PrefabRef & { class_name: string }>(
      `/unity/refs/${class_name}`, { params: { path } }).then(r => r.data),
}

export const llmApi = {
  getOllamaModels: (base_url = 'http://localhost:11434') =>
    api.get<{ models: string[]; ok: boolean }>('/llm/ollama/models', { params: { base_url } })
       .then(r => r.data),
  analyzeFlow: (flow_data: FlowData, breadcrumb: { cls: string; method: string }[],
                cfg: LLMConfig, flow_history: FlowData[] = []) =>
    api.post<{ result: string; ok: boolean }>('/llm/analyze', {
      flow_data, breadcrumb, flow_history,
      provider: cfg.provider, model: cfg.model,
      api_key: cfg.api_key ?? '', base_url: cfg.base_url ?? 'http://localhost:11434',
    }).then(r => r.data),
}

// ── UE5 Blueprint Refs ────────────────────────────────────────
export interface BlueprintRef {
  blueprints: string[]
  maps:       string[]
  total:      number
  module_name?: string
}

export const ue5Api = {
  getBlueprintRefs: (path: string) =>
    api.get<{ refs: Record<string, BlueprintRef>; total_classes: number; module_name: string }>
      ('/ue5/blueprint_refs', { params: { path } }).then(r => r.data),

  getClassBlueprintRefs: (path: string, class_name: string) =>
    api.get<BlueprintRef & { class_name: string }>(
      `/ue5/blueprint_refs/${class_name}`, { params: { path } }
    ).then(r => r.data),

  getBlueprintMapping: (path: string, cpp_class?: string) =>
    api.get<{ result: string; total?: number }>(
      '/ue5/blueprint_mapping', { params: { path, cpp_class: cpp_class ?? undefined } }
    ).then(r => r.data),
}


// ── 에이전트 SSE ──────────────────────────────────────────────

export function runAgent(
  sessionId: string, scriptsPath: string, question: string,
  llmConfig: LLMConfig, maxToolCalls: number,
  onEvent: (e: AgentEvent) => void, onDone: () => void,
) {
  fetch(`${BASE}/agent/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId, scripts_path: scriptsPath,
      question, max_tool_calls: maxToolCalls, llm_config: llmConfig,
    }),
  }).then(async res => {
    const reader  = res.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6).trim()
        if (data === '[DONE]') { onDone(); return }
        try { onEvent(JSON.parse(data)) } catch { /* skip */ }
      }
    }
    onDone()
  }).catch(err => { onEvent({ type: 'error', message: String(err) }); onDone() })
}

export async function resetAgent(sessionId: string) {
  return api.post('/agent/reset', { session_id: sessionId })
}

// ── Engine Analysis API (신규 기능) ───────────────────────────

export const engineApi = {
  // Unity Event 바인딩
  unityEvents: (path: string, method_name?: string) =>
    api.post<{ result: string }>('/engine/unity/events', { path, method_name: method_name ?? null })
       .then(r => r.data.result),

  // Unity Animator Controller
  unityAnimator: (path: string, controller_name?: string) =>
    api.post<{ result: string }>('/engine/unity/animator', { path, controller_name: controller_name ?? null })
       .then(r => r.data.result),

  // UE5 GAS (detail_level/category/query 지원)
  ue5Gas: (path: string, class_name?: string, detail_level = 'summary', category?: string, query?: string) =>
    api.post<{ result: string }>('/engine/ue5/gas', {
      path, class_name: class_name ?? null,
      detail_level, category: category ?? null, query: query ?? null,
    }).then(r => r.data.result),

  // UE5 GAS 연결 그래프 (ReactFlow용)
  ue5GasGraph: (path: string) =>
    api.post<{
      nodes: { id: string; label: string; type: string }[]
      edges: { from: string; to: string; relation: string }[]
      summary: { abilities: number; effects: number; attr_sets: number; tags: number; bp_abilities?: number; bp_effects?: number }
      error?: string
    }>('/engine/ue5/gas/graph', { path }).then(r => r.data),

  // UE5 Animation (ABP + Montage)
  ue5Animation: (path: string, asset_type = 'all', detail_level = 'summary', asset_name?: string) =>
    api.post<{ result: string }>('/engine/ue5/animation', {
      path, asset_type, detail_level, asset_name: asset_name ?? null,
    }).then(r => r.data.result),

  // UE5 BehaviorTree
  ue5BehaviorTree: (path: string, asset_name?: string) =>
    api.post<{ result: string }>('/engine/ue5/behavior_tree', { path, asset_name: asset_name ?? null })
       .then(r => r.data.result),

  // UE5 StateTree
  ue5StateTree: (path: string, asset_name?: string) =>
    api.post<{ result: string }>('/engine/ue5/state_tree', { path, asset_name: asset_name ?? null })
       .then(r => r.data.result),
}

// ── 신규 분석 API (Unity Event / Animator / UE5 GAS / ABP / BT / ST) ─────
export interface UnityEventBinding {
  method_name:  string
  class_name:   string
  source_asset: string
  mode:         number
}
export interface UnityEventResult {
  total_bindings:   number
  unique_methods:   number
  unique_classes:   number
  method_bindings:  Record<string, UnityEventBinding[]>
  raw_text:         string   // format_event_result 출력 그대로
}

export interface GASReport {
  raw_text: string   // analyze_gas 출력 그대로
}

export interface AnimationReport {
  raw_text: string   // analyze_abp / analyze_montage 출력
}

export interface AIReport {
  raw_text: string   // analyze_behavior_tree / analyze_state_tree 출력
}

export const engineAnalysisApi = {
  // Unity Event 바인딩
  unityEvents: (path: string, method_name?: string) =>
    api.post<{ result: string }>('/engine/unity/events', { path, method_name }).then(r => r.data),

  // Unity Animator
  unityAnimator: (path: string, controller_name?: string) =>
    api.post<{ result: string }>('/engine/unity/animator', { path, controller_name }).then(r => r.data),

  // UE5 GAS (detail_level/category/query 지원)
  ue5Gas: (path: string, class_name?: string, detail_level = 'summary', category?: string, query?: string) =>
    api.post<{ result: string }>('/engine/ue5/gas', {
      path, class_name, detail_level, category, query,
    }).then(r => r.data),

  // UE5 ABP + Montage
  ue5Animation: (path: string, asset_name?: string, asset_type = 'all', detail_level = 'summary') =>
    api.post<{ result: string }>('/engine/ue5/animation', { path, asset_name, asset_type, detail_level }).then(r => r.data),

  // UE5 BehaviorTree
  ue5BehaviorTree: (path: string, asset_name?: string) =>
    api.post<{ result: string }>('/engine/ue5/behavior_tree', { path, asset_name }).then(r => r.data),

  // UE5 StateTree
  ue5StateTree: (path: string, asset_name?: string) =>
    api.post<{ result: string }>('/engine/ue5/state_tree', { path, asset_name }).then(r => r.data),

  // Axmol Events
  axmolEvents: (path: string, method_name?: string) =>
    api.post<{ result: string }>('/engine/axmol/events', { path, method_name: method_name ?? null }).then(r => r.data),
}

// ── Stage 42: 신규 분석 API ────────────────────────────────────

export interface TestScopeFile {
  path:          string
  matched_class: string
  engine:        string
}

export interface TestScopeResult {
  target_class:    string
  affected_count:  number
  test_file_count: number
  test_files:      TestScopeFile[]
}

export interface LintFixIssue {
  rule_id:        string
  severity:       string
  message:        string
  class_name:     string
  method_name:    string
  file_path:      string
  fix_suggestion: string
}

export interface LintFixResult {
  total:   number
  fixable: number
  results: LintFixIssue[]
}

export const analysisApi = {
  testScope: (path: string, class_name: string, depth = 3) =>
    api.post<TestScopeResult>('/project/test-scope', { path, class_name, depth }).then(r => r.data),

  advise: (path: string, focus_class?: string, refresh = false) =>
    api.post<{ report: string }>('/project/advise', { path, focus_class: focus_class ?? null, refresh }).then(r => r.data),

  lintFix: (path: string, rule_ids?: string[]) =>
    api.post<LintFixResult>('/project/lint-fix', { path, rule_ids: rule_ids ?? null }).then(r => r.data),

  diffSummary: (path: string, commit?: string) =>
    api.post<{ report: string }>('/project/diff-summary', { path, commit: commit ?? null }).then(r => r.data),
}

// ── Analysis API (Phase 2: 신규 MCP 도구 대응) ───────────────

export const analysisNewApi = {
  hierarchy: (path: string, class_name: string, direction = 'both', max_depth = 10) =>
    api.post<{ result: string }>('/analysis/hierarchy', { path, class_name, direction, max_depth })
       .then(r => r.data.result),

  unusedAssets: (path: string, scan_dir?: string, max_results = 50) =>
    api.post<{ result: string }>('/analysis/unused-assets', { path, scan_dir: scan_dir ?? null, max_results })
       .then(r => r.data.result),

  queryApi: (path: string, query: string, scope = 'all', max_results = 20) =>
    api.post<{ result: string }>('/analysis/query-api', { path, query, scope, max_results })
       .then(r => r.data.result),

  detectPatterns: (path: string, max_results = 30) =>
    api.post<{ result: string }>('/analysis/detect-patterns', { path, max_results })
       .then(r => r.data.result),

  methodCallers: (path: string, class_name: string, method_name: string, max_results = 30) =>
    api.post<{ result: string }>('/analysis/method-callers', { path, class_name, method_name, max_results })
       .then(r => r.data.result),

  callPath: (path: string, from_class: string, from_method: string,
             to_class: string, to_method: string, depth = 10) =>
    api.post<{ result: string }>('/analysis/call-path',
      { path, from_class, from_method, to_class, to_method, depth })
       .then(r => r.data.result),

  exploreSemantics: (path: string, class_name: string, compact = true, include_source = false) =>
    api.post<{ result: string }>('/analysis/explore-semantics',
      { path, class_name, compact, include_source })
       .then(r => r.data.result),
}

// ── Wiki API ──────────────────────────────────────────────────

export interface WikiNode {
  id: string; type: string; title: string; file_path: string
  created_at: string; updated_at: string; stale: boolean
  meta: Record<string, unknown>
}
export interface WikiSearchResult { node: WikiNode; snippet: string; score: number }
export interface WikiNodeDetail { node: WikiNode; content: string }
export interface WikiGraphNode { id: string; label: string; type: string; stale: boolean }
export interface WikiGraphEdge { source: string; target: string; relation: string }
export interface WikiGraphData { nodes: WikiGraphNode[]; edges: WikiGraphEdge[] }
export interface WikiStats {
  types: Record<string, number>
  total_nodes: number
  total_edges: number
  stale_count: number
}

export const wikiApi = {
  stats: (path: string) =>
    api.get<WikiStats>('/wiki/stats', { params: { path } }).then(r => r.data),
  list: (path: string, type?: string, limit = 200) =>
    api.get<WikiNode[]>('/wiki/list', { params: { path, type: type || undefined, limit } }).then(r => r.data),
  search: (path: string, q: string, mode = 'or', type?: string, related = false, limit = 20) =>
    api.get<WikiSearchResult[]>('/wiki/search', { params: { path, q, mode, type: type || undefined, related, limit } }).then(r => r.data),
  node: (path: string, nodeId: string) =>
    api.get<WikiNodeDetail>('/wiki/node', { params: { path, node_id: nodeId } }).then(r => r.data),
  edges: (path: string, nodeId: string, relation?: string, depth = 1) =>
    api.get<WikiGraphEdge[]>('/wiki/edges', { params: { path, node_id: nodeId, relation: relation || undefined, depth } }).then(r => r.data),
  graph: (path: string, nodeId: string, depth = 1) =>
    api.get<WikiGraphData>('/wiki/graph', { params: { path, node_id: nodeId, depth } }).then(r => r.data),
}
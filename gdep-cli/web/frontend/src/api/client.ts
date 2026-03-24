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
export interface FlowEdge { from: string; to: string; context?: string; isDynamic?: boolean }
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

export const projectApi = {
  detect:     (path: string) =>
    api.get<ProjectInfo>('/project/detect', { params: { path } }).then(r => r.data),
  scan:       (path: string, top = 20, circular = true, dead_code = false, deep = false, include_refs = false) =>
    api.post<ScanResult>('/project/scan', { path, top, circular, dead_code, deep, include_refs }).then(r => r.data),
  describe:   (path: string, class_name: string) =>
    api.post<{ stdout: string }>('/project/describe', { path, class_name }).then(r => r.data),
  readSource: (path: string, class_name: string, max_chars = 8000) =>
    api.post<{ content: string }>('/project/read_source', { path, class_name, max_chars }).then(r => r.data),
  impact:     (path: string, target_class: string, depth = 3) =>
    api.post<ImpactResult>('/project/impact', { path, target_class, depth }).then(r => r.data),
  lint:       (path: string) =>
    api.post<LintResult>('/project/lint', { path }).then(r => r.data),
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

  // UE5 GAS
  ue5Gas: (path: string, class_name?: string) =>
    api.post<{ result: string }>('/engine/ue5/gas', { path, class_name: class_name ?? null })
       .then(r => r.data.result),

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

  // UE5 GAS
  ue5Gas: (path: string, class_name?: string) =>
    api.post<{ result: string }>('/engine/ue5/gas', { path, class_name }).then(r => r.data),

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
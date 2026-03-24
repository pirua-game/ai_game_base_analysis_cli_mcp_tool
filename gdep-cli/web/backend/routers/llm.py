"""
/api/llm
Ollama 모델 자동 감지 + 흐름 해석
"""
from __future__ import annotations
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

router = APIRouter()


@router.get("/ollama/models")
def list_ollama_models(base_url: str = "http://localhost:11434"):
    """Ollama 설치 모델 목록 반환"""
    try:
        import requests
        resp = requests.get(f"{base_url}/api/tags", timeout=3)
        if resp.ok:
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"models": models, "ok": True}
    except Exception:
        pass
    return {"models": [], "ok": False}


class LLMAnalyzeRequest(BaseModel):
    flow_data:        dict
    breadcrumb:       list[dict]        # [{cls, method}] — 현재까지의 드릴다운 경로
    flow_history:     list[dict] = []   # 각 단계의 flow_data (breadcrumb 순서와 동일)
    provider:    str = "ollama"
    model:       str = "qwen2.5-coder:14b"
    api_key:     str = ""
    base_url:    str = "http://localhost:11434"


def _build_prompt(flow_data: dict, breadcrumb: list[dict],
                  flow_history: list[dict] | None = None) -> str:
    # ── 드릴다운 경로 요약 ────────────────────────────────────
    bc_str = " → ".join(f"{b['cls']}.{b['method']}" for b in breadcrumb) if breadcrumb else flow_data.get("entry", "?")
    current_entry = breadcrumb[-1] if breadcrumb else None
    current_label = f"{current_entry['cls']}.{current_entry['method']}" if current_entry else flow_data.get("entry", "?")

    # ── 상위 단계 호출 흐름 요약 (history) ───────────────────
    history_section = ""
    if flow_history:
        history_lines = []
        for i, hist in enumerate(flow_history[:-1]):  # 현재 단계 제외
            step_bc = breadcrumb[i] if i < len(breadcrumb) else None
            step_label = f"{step_bc['cls']}.{step_bc['method']}" if step_bc else f"Step {i+1}"
            callers = [
                f"{e['from'].split('.')[-1]} → {e['to'].split('.')[-1]}"
                for e in hist.get("edges", [])
                if e['to'].split('.')[-1] == (breadcrumb[i+1]['method'] if i+1 < len(breadcrumb) else '')
            ][:3]
            history_lines.append(
                f"  [{i+1}] {step_label}"
                + (f" (calls: {', '.join(callers)})" if callers else "")
            )
        if history_lines:
            history_section = "## 상위 호출 단계\n" + "\n".join(history_lines) + "\n\n"

    # ── 현재 단계 노드/엣지 ──────────────────────────────────
    nodes = "\n".join(
        f"- {n.get('label', n.get('method','?'))}"
        for n in flow_data.get("nodes", [])
        if not n.get("isLeaf") and not n.get("isDispatch")
    )
    edges = "\n".join(
        f"- {e['from'].split('.')[-1]} → {e['to'].split('.')[-1]}"
        + (f" [{e['context']}]" if e.get("context") else "")
        for e in flow_data.get("edges", [])
    )
    dispatches = "\n".join(
        f"- {d['from'].split('.')[-1]}: {d['handler']}"
        for d in flow_data.get("dispatches", [])
    )
    dispatch_section = f"\n## 동적 디스패치\n{dispatches}" if dispatches else ""

    depth_note = f"(드릴다운 {len(breadcrumb)}단계)" if len(breadcrumb) > 1 else ""

    return f"""게임 클라이언트 코드베이스 메서드 호출 흐름 분석입니다 {depth_note}.

## 전체 드릴다운 경로
{bc_str}

{history_section}## 현재 분석 대상: `{current_label}`
### 호출 메서드
{nodes[:1500]}

### 호출 관계
{edges[:2000]}
{dispatch_section}

한국어로 분석해주세요:
1. **전체 흐름 요약**: {bc_str} — 이 호출 체인이 하는 일 (2~3문장)
2. **현재 함수 `{current_label}` 역할**: 이 함수가 전체 흐름에서 맡은 책임
3. **주요 흐름 단계**: 번호 목록으로
4. **설계 주의점**: 이 흐름에서 리팩터링 시 주의할 점

간결하고 실용적으로."""


@router.post("/analyze")
def analyze_flow(req: LLMAnalyzeRequest):
    """흐름 데이터를 LLM으로 분석"""
    prompt = _build_prompt(req.flow_data, req.breadcrumb, req.flow_history)

    try:
        if req.provider == "ollama":
            import requests
            resp = requests.post(
                f"{req.base_url}/api/generate",
                json={"model": req.model, "prompt": prompt, "stream": False},
                timeout=120,
            )
            if resp.ok:
                return {"result": resp.json().get("response", "응답 없음"), "ok": True}
            return {"result": f"Ollama 오류: {resp.status_code}", "ok": False}

        elif req.provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=req.api_key)
            resp   = client.chat.completions.create(
                model=req.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return {"result": resp.choices[0].message.content, "ok": True}

        elif req.provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=req.api_key)
            msg    = client.messages.create(
                model=req.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return {"result": msg.content[0].text, "ok": True}

        else:
            return {"result": f"지원하지 않는 프로바이더: {req.provider}", "ok": False}

    except Exception as e:
        return {"result": f"오류: {e}", "ok": False}
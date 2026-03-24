"""
/api/agent
AI 에이전트 — SSE(Server-Sent Events) 스트리밍
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from gdep.agent import gdepAgent
from gdep.llm_provider import LLMConfig

router = APIRouter()

# 세션별 에이전트 캐시 (메모리)
_agents: dict[str, gdepAgent] = {}


class AgentRequest(BaseModel):
    session_id:    str
    scripts_path:  str
    question:      str
    max_tool_calls: int = 4
    llm_config: dict = {}   # provider, model, api_key, base_url


class AgentResetRequest(BaseModel):
    session_id: str


def _get_agent(session_id: str, scripts_path: str,
               llm_cfg: LLMConfig) -> gdepAgent:
    key = f"{session_id}::{scripts_path}::{llm_cfg.provider}::{llm_cfg.model}"
    if key not in _agents:
        _agents[key] = gdepAgent(
            scripts_path=scripts_path,
            model=llm_cfg.model,
            llm_config=llm_cfg,
        )
    return _agents[key]


@router.post("/run")
def run_agent(req: AgentRequest):
    """
    에이전트 실행 — SSE 스트리밍.
    각 이벤트는 JSON 라인으로 전송됩니다.
    event types: tool_call | tool_result | answer | error
    """
    cfg_data = req.llm_config or {}
    llm_cfg  = LLMConfig(
        provider=cfg_data.get("provider", "ollama"),
        model=cfg_data.get("model", "qwen2.5-coder:14b"),
        api_key=cfg_data.get("api_key", ""),
        base_url=cfg_data.get("base_url", "http://localhost:11434"),
    )
    agent = _get_agent(req.session_id, req.scripts_path, llm_cfg)

    def event_stream():
        try:
            for event in agent.run(req.question,
                                   max_tool_calls=req.max_tool_calls,
                                   llm_config=llm_cfg):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/reset")
def reset_agent(req: AgentResetRequest):
    """에이전트 대화 초기화"""
    keys_to_del = [k for k in _agents if k.startswith(req.session_id + "::")]
    for k in keys_to_del:
        del _agents[k]
    return {"reset": len(keys_to_del)}


@router.get("/history")
def get_history(session_id: str, scripts_path: str, provider: str = "ollama",
                model: str = "qwen2.5-coder:14b"):
    """대화 히스토리 반환"""
    key = f"{session_id}::{scripts_path}::{provider}::{model}"
    agent = _agents.get(key)
    if not agent:
        return {"history": []}
    return {"history": [
        {"role": m["role"], "content": m.get("content", "")}
        for m in agent.history
        if m["role"] in ("user", "assistant") and m.get("content", "").strip()
    ]}

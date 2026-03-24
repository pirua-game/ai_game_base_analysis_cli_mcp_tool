"""
gdep.llm_provider
Abstraction layer for Ollama / OpenAI / Gemini / Claude APIs.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


@dataclass
class LLMConfig:
    provider: str       # "ollama" | "openai" | "gemini" | "claude"
    model: str
    api_key: str = ""
    base_url: str = "http://localhost:11434"


def get_config_path() -> Path:
    """Returns the path where configuration is stored in the user's home directory."""
    path = Path.home() / ".gdep" / "llm_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_config() -> LLMConfig | None:
    path = get_config_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LLMConfig(**data)
    except Exception:
        return None


def save_config(config: LLMConfig):
    path = get_config_path()
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")


def list_ollama_models(base_url: str = "http://localhost:11434") -> list[str]:
    """Returns a list of models installed in Ollama."""
    if requests is None:
        return []
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        if resp.ok:
            return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass
    return []


def chat(config: LLMConfig, messages: list[dict],
         tools: list[dict] | None = None) -> dict:
    """
    Calls the LLM API and returns the response in a unified Ollama-like format.
    Return format: {"message": {"role": "assistant", "content": "...", "tool_calls": [...]}}
    """
    if config.provider == "ollama":
        return _chat_ollama(config, messages, tools)
    elif config.provider == "openai":
        return _chat_openai(config, messages, tools)
    elif config.provider == "gemini":
        return _chat_gemini(config, messages, tools)
    elif config.provider == "claude":
        return _chat_claude(config, messages, tools)
    else:
        raise ValueError(f"Unsupported provider: {config.provider}")


# ── Ollama ────────────────────────────────────────────────────

def _chat_ollama(config: LLMConfig, messages: list[dict],
                 tools: list[dict] | None) -> dict:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools

    if requests is None:
        raise ImportError("'requests' package is required for Ollama. Install it with: pip install requests")
    resp = requests.post(f"{config.base_url}/api/chat",
                         json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json()


# ── OpenAI ────────────────────────────────────────────────────

def _chat_openai(config: LLMConfig, messages: list[dict],
                 tools: list[dict] | None) -> dict:
    import openai
    client = openai.OpenAI(api_key=config.api_key)

    kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    resp = client.chat.completions.create(**kwargs)
    msg  = resp.choices[0].message

    # Convert to Ollama-like format
    tool_calls = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            tool_calls.append({
                "function": {
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments or "{}"),
                }
            })

    return {
        "message": {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": tool_calls,
        }
    }


# ── Gemini ────────────────────────────────────────────────────

def _chat_gemini(config: LLMConfig, messages: list[dict],
                 tools: list[dict] | None) -> dict:
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError("Please run: pip install google-generativeai")

    genai.configure(api_key=config.api_key)
    model = genai.GenerativeModel(config.model)

    # Gemini handles system messages separately
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    history = []
    for m in messages:
        if m["role"] == "system":
            continue
        role = "user" if m["role"] == "user" else "model"
        history.append({"role": role, "parts": [m["content"]]})

    chat_session = model.start_chat(history=history[:-1] if history else [])
    last_msg = history[-1]["parts"][0] if history else ""
    resp = chat_session.send_message(last_msg)

    return {
        "message": {
            "role": "assistant",
            "content": resp.text,
            "tool_calls": [],
        }
    }


# ── Claude ────────────────────────────────────────────────────

def _chat_claude(config: LLMConfig, messages: list[dict],
                 tools: list[dict] | None) -> dict:
    try:
        import anthropic
    except ImportError:
        raise ImportError("Please run: pip install anthropic")

    client = anthropic.Anthropic(api_key=config.api_key)

    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    filtered = [m for m in messages if m["role"] != "system"]

    # Convert messages to Claude format
    claude_msgs = []
    for m in filtered:
        if m["role"] == "tool":
            claude_msgs.append({
                "role": "user",
                "content": [{"type": "tool_result",
                              "tool_use_id": "tool_0",
                              "content": m["content"]}]
            })
        else:
            claude_msgs.append({"role": m["role"], "content": m["content"]})

    kwargs: dict[str, Any] = {
        "model": config.model,
        "max_tokens": 2048,
        "system": system,
        "messages": claude_msgs,
    }

    # Convert tools to Claude format
    if tools:
        claude_tools = []
        for t in tools:
            f = t.get("function", {})
            claude_tools.append({
                "name": f["name"],
                "description": f.get("description", ""),
                "input_schema": f.get("parameters", {}),
            })
        kwargs["tools"] = claude_tools

    resp = client.messages.create(**kwargs)

    # Convert to Ollama-like format
    content_text = ""
    tool_calls = []
    for block in resp.content:
        if block.type == "text":
            content_text += block.text
        elif block.type == "tool_use":
            tool_calls.append({
                "function": {
                    "name": block.name,
                    "arguments": block.input,
                }
            })

    return {
        "message": {
            "role": "assistant",
            "content": content_text,
            "tool_calls": tool_calls,
        }
    }


# ── Provider Metadata ──────────────────────────────────────

PROVIDER_INFO = {
    "ollama": {
        "label":       "Ollama (Local)",
        "needs_key":   False,
        "default_models": ["qwen2.5-coder:14b", "llama3", "gemma3:12b"],
        "key_placeholder": "",
    },
    "openai": {
        "label":       "OpenAI",
        "needs_key":   True,
        "default_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "key_placeholder": "sk-...",
    },
    "gemini": {
        "label":       "Google Gemini",
        "needs_key":   True,
        "default_models": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
        "key_placeholder": "AIza...",
    },
    "claude": {
        "label":       "Anthropic Claude",
        "needs_key":   True,
        "default_models": ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
        "key_placeholder": "sk-ant-...",
    },
}


def summarize_class(class_name: str, context: str) -> str:
    """Generates a 3-line summary based on class information."""
    config = load_config()
    if not config:
        return "LLM configuration not found. Please set it using the 'gdep config llm' command."

    prompt = f"""You are an expert game software architect.
Analyze the structure (fields, methods, etc.) of the following class and summarize its **main roles and responsibilities** in a 3-line English summary.

Class Name: {class_name}
Details:
{context}

Summary Guidelines:
- Line 1: The essential identity of the class (e.g., Data Container, Singleton Manager, UI Controller, etc.)
- Line 2: Core business logic or functionality.
- Line 3: Key interactions with other systems or design characteristics.
- You MUST write exactly 3 lines, with each line ending as a concise sentence.
"""
    try:
        # system message: Gemini/Claude extract it separately; Ollama/OpenAI accept it in messages array
        messages = [
            {"role": "system", "content": "You are a specialist in summarizing class roles clearly and concisely."},
            {"role": "user", "content": prompt}
        ]
        resp = chat(config, messages)
        return resp["message"]["content"].strip()
    except ImportError as e:
        return f"Missing dependency for provider '{config.provider}': {str(e)}"
    except Exception as e:
        return f"Failed to generate summary (provider={config.provider}, model={config.model}): {str(e)}"

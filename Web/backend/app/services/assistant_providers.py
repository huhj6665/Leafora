"""External providers: private credentials never enter model prompts or results."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import AsyncIterator

import httpx
import jwt

from app.core.config import settings


class ProviderError(Exception):
    pass


def capabilities() -> dict:
    weather = bool(settings.QWEATHER_API_HOST and (settings.QWEATHER_API_KEY or (
        settings.QWEATHER_KEY_ID and settings.QWEATHER_PROJECT_ID and settings.QWEATHER_PRIVATE_KEY_PATH)))
    return {"model": settings.DEEPSEEK_MODEL, "model_configured": bool(settings.DEEPSEEK_API_KEY),
            "weather_configured": weather, "search_configured": bool(settings.TAVILY_API_KEY),
            "vision_supported": settings.DEEPSEEK_MODEL == "deepseek-flash",
            "limits": {"images": 3, "document_mb": 20, "image_mb": 10, "run_seconds": settings.ASSISTANT_RUN_TIMEOUT_SECONDS}}


def weather_headers() -> dict:
    if settings.QWEATHER_PRIVATE_KEY_PATH:
        now = int(time.time())
        token = jwt.encode({"sub": settings.QWEATHER_PROJECT_ID, "iat": now - 30, "exp": now + 600},
                           Path(settings.QWEATHER_PRIVATE_KEY_PATH).read_text(encoding="utf-8"),
                           algorithm="EdDSA", headers={"kid": settings.QWEATHER_KEY_ID})
        return {"Authorization": "Bearer " + token}
    return {"X-QW-Api-Key": settings.QWEATHER_API_KEY}


async def weather_request(path: str, params: dict | None = None) -> dict:
    if not capabilities()["weather_configured"]:
        raise ProviderError("天气服务尚未配置，无法查询实时天气")
    host = settings.QWEATHER_API_HOST.removeprefix("https://").rstrip("/")
    if not re.fullmatch(r"[a-zA-Z0-9.-]+\.qweatherapi\.com", host):
        raise ProviderError("天气服务API Host配置无效")
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get("https://" + host + path, params=params, headers=weather_headers())
            response.raise_for_status()
            data = response.json()
        if str(data.get("code", "200")) != "200":
            raise ProviderError("天气服务未返回有效结果，请检查地点与服务权限")
        return data
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError("天气服务暂时不可用，请稍后重试") from exc


async def web_search(query: str, trusted_only: bool = True) -> list[dict]:
    if not settings.TAVILY_API_KEY:
        raise ProviderError("联网搜索尚未配置，无法核实最新资料")
    # Query must describe public agricultural knowledge, never include platform records.
    domains = ["agri.cn", "moa.gov.cn", "natesc.org.cn", "caas.cn", "tobacco.gov.cn", "fao.org"]
    body = {"query": query, "max_results": 5, "search_depth": "basic",
            "include_answer": False, "include_raw_content": "text"}
    if trusted_only:
        body["include_domains"] = domains
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post("https://api.tavily.com/search", json=body,
                                         headers={"Authorization": "Bearer " + settings.TAVILY_API_KEY})
            response.raise_for_status()
            data = response.json()
        return [{"title": x.get("title", "资料"), "url": x.get("url"),
                 "text": (x.get("raw_content") or x.get("content") or "")[:6000],
                 "published_at": x.get("published_date")} for x in data.get("results", [])[:5]]
    except Exception as exc:
        raise ProviderError("联网搜索暂时不可用，请稍后重试") from exc


async def model_stream(messages: list[dict], tools: list[dict]) -> AsyncIterator[dict]:
    """Normalize provider SSE; assemble fragmented tool calls before execution."""
    body = {"model": settings.DEEPSEEK_MODEL, "messages": messages, "stream": True,
            "stream_options": {"include_usage": True}, "max_tokens": 5000,
            "thinking": {"type": "disabled"}, "temperature": 0.2}
    if tools:
        body.update(tools=tools, tool_choice="auto")
    calls: dict[int, dict] = {}
    content = ""
    usage: dict = {}
    try:
        timeout = httpx.Timeout(settings.ASSISTANT_MODEL_TIMEOUT_SECONDS, connect=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", settings.DEEPSEEK_API_URL,
                                     headers={"Authorization": "Bearer " + settings.DEEPSEEK_API_KEY}, json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    packet = json.loads(payload)
                    if packet.get("usage"):
                        usage = packet["usage"]
                    for choice in packet.get("choices", []):
                        delta = choice.get("delta", {})
                        if delta.get("content"):
                            content += delta["content"]
                            yield {"kind": "delta", "text": delta["content"]}
                        for piece in delta.get("tool_calls", []):
                            index = piece["index"]
                            call = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            if piece.get("id"):
                                call["id"] = piece["id"]
                            for key in ("name", "arguments"):
                                call["function"][key] += piece.get("function", {}).get(key) or ""
        yield {"kind": "complete", "message": {"role": "assistant", "content": content or None,
                                                 **({"tool_calls": list(calls.values())} if calls else {})}, "usage": usage}
    except Exception as exc:
        raise ProviderError("模型服务暂时不可用，请检查配置、额度或网络后重试") from exc

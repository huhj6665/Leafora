"""AI 辅助服务。

AI 永不持有数据库会话，只接收 AnalysisService 产出的最小化结构化结果，
从架构层阻断模型直接访问数据库或用户凭据。
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


def _local_answer(question: str, context: dict[str, Any]) -> str:
    metrics = context.get("metrics", {})
    latest = context.get("recent_events", [])
    if not latest and not metrics.get("samples"):
        return "当前还没有可分析的巡检数据。建议先绑定设备并完成一次巡检，随后我可以根据轨迹、环境变化和检测结果生成摘要。"
    event_text = f"最近一次巡检为“{latest[0]['name']}”，状态 {latest[0]['status']}。" if latest else ""
    return (
        f"基于平台结构化数据：累计 {metrics.get('events', 0)} 次巡检、"
        f"{metrics.get('samples', 0)} 个采样点，当前有 {metrics.get('active_events', 0)} 个任务运行中。"
        f"{event_text}针对“{question}”，建议优先查看巡检地图中的异常聚集区域，并结合温湿度、CO₂ 与光照趋势复核。"
        "该建议仅用于巡检辅助，不替代专业农业诊断。"
    )


async def answer(question: str, context: dict[str, Any]) -> dict[str, Any]:
    if not settings.DEEPSEEK_API_KEY:
        return {"answer": _local_answer(question, context), "provider": "local", "model": "structured-rules"}
    prompt = {
        "role": "user",
        "content": (
            "你是农业智能巡检平台的辅助分析助手。只根据给定 JSON 摘要回答，"
            "不要声称做出专业农业诊断，不要推测个人信息。用简洁中文给出观察与下一步建议。\n"
            f"问题：{question}\n结构化摘要：{context}"
        ),
    }
    async with httpx.AsyncClient(timeout=settings.DEEPSEEK_TIMEOUT_SECONDS) as client:
        response = await client.post(
            settings.DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}"},
            json={"model": settings.DEEPSEEK_MODEL, "messages": [prompt], "temperature": 0.2},
        )
        response.raise_for_status()
        data = response.json()
    return {
        "answer": data["choices"][0]["message"]["content"],
        "provider": "deepseek",
        "model": settings.DEEPSEEK_MODEL,
    }

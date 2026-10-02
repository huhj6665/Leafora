"""Explicit, owner-scoped read tools. No arbitrary SQL, HTTP or filesystem tool."""
from __future__ import annotations

import asyncio
import base64
import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi.encoders import jsonable_encoder
from pydantic import ConfigDict, Field as SchemaField, create_model
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError
from app.models.assistant import AssistantFieldContext
from app.models.field import Field
from app.models.inspection import (CloudDetection, DetectionRecord, DetectionResult, EnvironmentRecord,
                                   ImageRecord, InspectionEvent, InspectionRecord)
from app.services import assistant_files, assistant_providers, device_service, field_service, task_service
from app.services.image_storage import resolve_path


def arg(annotation, default=None, **kwargs):
    return annotation, SchemaField(default, **kwargs)


ID = arg(str | None, None, max_length=64)
PARAMETERS = {
    "list_fields": {"query": arg(str, "", max_length=100)},
    "get_field_context": {"field_id": arg(str, ..., max_length=64)},
    "list_devices": {},
    "get_device_status": {"device_id": arg(str, ..., max_length=64)},
    "list_inspections": {"field_id": ID, "device_id": ID, "status": arg(str | None, None, max_length=20),
                         "start_date": arg(str | None, None, max_length=30), "end_date": arg(str | None, None, max_length=30),
                         "page": arg(int, 1, ge=1, le=10000), "page_size": arg(int, 10, ge=1, le=30)},
    "get_inspection_summary": {"inspection_id": arg(str, ..., max_length=64)},
    "get_detection_statistics": {"inspection_id": arg(str, ..., max_length=64)},
    "get_environment_summary": {"inspection_id": arg(str, ..., max_length=64)},
    "get_spatial_risk_summary": {"inspection_id": arg(str, ..., max_length=64), "limit": arg(int, 8, ge=1, le=20)},
    "compare_inspections": {"first_id": arg(str, ..., max_length=64), "second_id": arg(str, ..., max_length=64)},
    "resolve_location": {"query": arg(str, ..., min_length=2, max_length=100)},
    "get_weather": {"latitude": arg(float, ..., ge=-90, le=90), "longitude": arg(float, ..., ge=-180, le=180),
                    "location_name": arg(str, ..., max_length=100), "days": arg(int, 3, ge=1, le=7)},
    "get_weather_alerts": {"latitude": arg(float, ..., ge=-90, le=90), "longitude": arg(float, ..., ge=-180, le=180),
                           "location_name": arg(str, ..., max_length=100)},
    "search_knowledge": {"query": arg(str, ..., min_length=2, max_length=300)},
    "search_web": {"query": arg(str, ..., min_length=2, max_length=200), "trusted_only": arg(bool, True)},
    "read_authorized_image": {"image_id": arg(str, ..., max_length=64)},
}
LABELS = {
    "list_fields": "查询烟田", "get_field_context": "读取烟田背景", "list_devices": "查询设备",
    "get_device_status": "读取设备状态", "list_inspections": "查找巡检",
    "get_inspection_summary": "汇总巡检", "get_detection_statistics": "统计识别结果",
    "get_environment_summary": "分析环境数据", "get_spatial_risk_summary": "查询风险分区",
    "compare_inspections": "比较两次巡检", "resolve_location": "确认天气地点",
    "get_weather": "获取天气预报", "get_weather_alerts": "获取天气预警",
    "search_knowledge": "检索知识资料", "search_web": "搜索农业资料", "read_authorized_image": "查看授权图片",
}
DESCRIPTIONS = {
    "list_fields": "按名称查找用户烟田，不返回真实位置；先查此工具以确认field_id。",
    "get_field_context": "烟田农业背景。SIMULATED位置不可用于真实天气查询。",
    "list_devices": "当前用户设备的通信、运行、同步状态，无控制能力。",
    "get_device_status": "设备最新展示摘要，包含陈旧度，不返回原始JSON或凭据。",
    "list_inspections": "按烟田、设备、状态和日期分页查巡检；日期区间end_date含当日。",
    "get_inspection_summary": "巡检状态、样本及来源分离的识别统计、环境摘要，不包含所有原始采样。",
    "get_detection_statistics": "识别类别和来源分开计数。不同来源不能直接相加为病害发生率。",
    "get_environment_summary": "环境有效数、缺失数、范围、均值与时间序列；未配置作物阈值不判异常。",
    "get_spatial_risk_summary": "按现有公式查询空间分区与图片证据；风险分不是病害发生率。",
    "compare_inspections": "比较两次巡检；不同烟田不可比较，同田版本不一致不直接比较分区。",
    "resolve_location": "解析用户明确指定的地区，重名时向用户显示候选，不使用模拟坐标。",
    "get_weather": "先resolve_location取得真实地点坐标，再查询当前天气、逐小时及每日预报；不得猜坐标。",
    "get_weather_alerts": "查询指定地点有效官方预警；无预警不是无天气风险。",
    "search_knowledge": "中文检索公共知识与自己的文档，返回原文片段及页码/段落。可改写关键词重试。",
    "search_web": "只搜索公共农业知识，不得传入用户名称、位置坐标、平台ID、私有文档或统计。",
    "read_authorized_image": "用户明确允许图片分析时读取授权病害图片，最多3张，不覆盖检测结果。",
}
ARGUMENT_MODELS = {name: create_model(name + "Args", __config__=ConfigDict(extra="forbid"), **params)
                   for name, params in PARAMETERS.items()}


def tool_definitions(web_enabled: bool, image_enabled: bool) -> list[dict]:
    return [{"type": "function", "function": {"name": name, "description": DESCRIPTIONS[name],
            "parameters": ARGUMENT_MODELS[name].model_json_schema()}} for name in PARAMETERS
            if (name != "search_web" or web_enabled) and (name != "read_authorized_image" or image_enabled)]


async def owned_event(db: AsyncSession, user_id: int, inspection_id: str) -> InspectionEvent:
    event = await db.scalar(select(InspectionEvent).where(InspectionEvent.inspection_id == inspection_id,
                                                       InspectionEvent.owner_user_id == user_id))
    if not event:
        raise NotFoundError("巡检不存在或无权访问")
    return event


def event_dict(event: InspectionEvent) -> dict:
    return jsonable_encoder({"inspection_id": event.inspection_id, "name": event.name, "status": event.status,
        "field_id": event.field_id, "field_version": event.field_version, "device_id": event.device_id,
        "started_at": event.started_at, "ended_at": event.ended_at, "created_at": event.created_at,
        "data_provenance": event.data_provenance, "run_mode": event.run_mode,
        "sync_status": event.sync_status, "pending_sync_count": event.pending_sync_count})


async def environment(db: AsyncSession, event: InspectionEvent) -> dict:
    fields = {"temperature": "°C", "humidity": "%", "co2": "ppm", "light": "原始传感器单位"}
    total = await db.scalar(select(func.count(InspectionRecord.id)).where(InspectionRecord.event_id == event.id)) or 0
    metrics = {}
    for name, unit in fields.items():
        column = getattr(EnvironmentRecord, name)
        result = (await db.execute(select(func.count(column), func.min(column), func.max(column), func.avg(column))
                  .join(InspectionRecord, InspectionRecord.id == EnvironmentRecord.inspection_id)
                  .where(InspectionRecord.event_id == event.id, EnvironmentRecord.valid.is_(True),
                         column > float('-inf'), column < float('inf')))).one()
        count, low, high, mean = result
        metrics[name] = {"valid_count": count, "missing_count": total - count,
                         "min": low, "max": high, "mean": round(mean, 3) if mean is not None and math.isfinite(mean) else None,
                         "unit": unit}
    rows = (await db.execute(select(EnvironmentRecord, InspectionRecord.captured_at)
            .join(InspectionRecord, InspectionRecord.id == EnvironmentRecord.inspection_id)
            .where(InspectionRecord.event_id == event.id, EnvironmentRecord.valid.is_(True))
            .order_by(InspectionRecord.captured_at.desc()).limit(120))).all()
    series = [{"time": captured.isoformat(), **{name: getattr(env, name) if getattr(env, name) is not None
               and math.isfinite(getattr(env, name)) else None for name in fields}} for env, captured in reversed(rows)]
    return {"metrics": metrics, "series": series, "series_scope": "最近120个环境记录，非全部巡检曲线",
            "sample_count": total, "note": "无已审核作物阈值；只提供客观统计，不判定作物异常"}


async def detections(db: AsyncSession, event: InspectionEvent) -> dict:
    edge = (await db.execute(select(DetectionResult.class_name, func.count(DetectionResult.id))
            .join(DetectionRecord, DetectionRecord.id == DetectionResult.detection_id)
            .join(InspectionRecord, InspectionRecord.id == DetectionRecord.inspection_id)
            .where(InspectionRecord.event_id == event.id).group_by(DetectionResult.class_name))).all()
    cloud_stmt = select(CloudDetection.results).join(ImageRecord, ImageRecord.id == CloudDetection.image_id)
    cloud_stmt = cloud_stmt.join(InspectionRecord, InspectionRecord.id == ImageRecord.inspection_id)
    cloud = (await db.execute(cloud_stmt.where(InspectionRecord.event_id == event.id,
                           CloudDetection.status == "completed").limit(2001))).scalars().all()
    counts = Counter(item.get("class", "未知") for results in cloud[:2000] for item in (results or []))
    images = await db.scalar(select(func.count(ImageRecord.id)).join(InspectionRecord, InspectionRecord.id == ImageRecord.inspection_id)
                             .where(InspectionRecord.event_id == event.id)) or 0
    status_counts = (await db.execute(select(CloudDetection.status, func.count(CloudDetection.id))
                     .join(ImageRecord, ImageRecord.id == CloudDetection.image_id)
                     .join(InspectionRecord, InspectionRecord.id == ImageRecord.inspection_id)
                     .where(InspectionRecord.event_id == event.id).group_by(CloudDetection.status))).all()
    edge_reports = await db.scalar(select(func.count(DetectionRecord.id))
        .join(InspectionRecord, InspectionRecord.id == DetectionRecord.inspection_id)
        .where(InspectionRecord.event_id == event.id)) or 0
    return {"edge_classes": dict(edge), "edge_target_count": sum(count for _, count in edge),
            "edge_report_count": edge_reports, "cloud_status_counts": dict(status_counts),
            "cloud_classes": dict(counts), "cloud_target_count": sum(counts.values()), "image_record_count": images,
            "cloud_scope": "最多2000张已完成云端识别图片", "cloud_truncated": len(cloud) > 2000,
            "note": "边缘与云端分开统计，图片记录可包含标注副本；未完成或失败识别不等于健康，目标数不是病株数或病害发生率"}


class ToolExecutor:
    def __init__(self, db: AsyncSession, user_id: int, request: dict):
        self.db, self.user_id, self.request = db, user_id, request
        self.evidence: list[dict] = []
        self.images: list[dict] = []
        self.image_count = 0
        self.search_count = 0
        self.private_terms: set[str] = set()
        self.location_hints = request.get("question", "") + " " + (request.get("context") or {}).get("location", "")
        self.resolved_locations: list[dict] = []

    def cite(self, title: str, kind: str, data, url: str | None = None, **extra) -> str:
        identifier = f"E{len(self.evidence) + 1}"
        evidence = {"id": identifier, "title": title, "kind": kind, "url": url,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(), "data": data, **extra}
        # Serialize strictly: NaN/Infinity are not sent to model or browser.
        self.evidence.append(jsonable_encoder(evidence))
        return identifier

    async def execute(self, name: str, arguments: str) -> dict:
        if name not in ARGUMENT_MODELS:
            return {"error": "工具不存在"}
        try:
            args = ARGUMENT_MODELS[name].model_validate_json(arguments).model_dump()
            data, title, kind, url = await self._execute(name, args)
            data = jsonable_encoder(data)
            identifier = self.cite(title, kind, data, url)
            return {"evidence_id": identifier, "data": data}
        except (BusinessError, assistant_providers.ProviderError) as exc:
            return {"error": str(exc)}
        except Exception:
            return {"error": "工具参数无效或查询暂时失败，请修正参数或说明缺少的数据"}

    async def _execute(self, name: str, a: dict):
        db, uid = self.db, self.user_id
        if name == "list_fields":
            rows = (await db.execute(select(Field).where(Field.owner_user_id == uid,
                     Field.name.contains(a["query"])).limit(100))).scalars().all()
            data = [{"field_id": r.field_id, "name": r.name, "version": r.version, "status": r.status,
                     "calibration_status": r.calibration_status} for r in rows]
            self.private_terms.update(r.name for r in rows)
            return data, "烟田列表", "platform", "/platform/fields"
        if name == "get_field_context":
            row = await field_service.owned_field(db, uid, a["field_id"])
            saved = await db.scalar(select(AssistantFieldContext).where(AssistantFieldContext.owner_user_id == uid,
                                                            AssistantFieldContext.field_id == row.field_id))
            self.private_terms.add(row.name)
            if saved and saved.context.get("location"):
                self.location_hints += " " + saved.context["location"]
            return {"field_id": row.field_id, "name": row.name, "version": row.version,
                    "calibration_status": row.calibration_status, "data_source": row.data_source,
                    "agricultural_context": saved.context if saved else {},
                    "weather_location_required": not saved or not saved.context.get("location")}, row.name, "platform", f"/platform/fields/{row.field_id}"
        if name == "list_devices":
            data = await device_service.list_user_devices(db, uid)
            return data, "已绑定设备", "platform", "/platform/devices"
        if name == "get_device_status":
            data = await task_service.live_by_device(db, uid, a["device_id"])
            data = {key: data[key] for key in ("device_id", "received_at", "age_ms", "link_state", "device_state") if key in data} | {"display": {
                key: value for key, value in (data.get("display") or {}).items()
                if key in {"environment", "device_status", "flight_status", "data_provenance", "timestamp"}}}
            return data, "设备最新状态", "platform", "/platform/live"
        if name == "list_inspections":
            conditions = [InspectionEvent.owner_user_id == uid]
            for key in ("field_id", "device_id", "status"):
                if a[key]:
                    conditions.append(getattr(InspectionEvent, key) == a[key])
            if a["field_id"]:
                await field_service.owned_field(db, uid, a["field_id"])
            for key, lower in (("start_date", True), ("end_date", False)):
                if a[key]:
                    value = datetime.fromisoformat(a[key].replace("Z", "+00:00"))
                    value = value if value.tzinfo else value.replace(tzinfo=timezone(timedelta(hours=8)))
                    if not lower and len(a[key]) == 10:
                        value += timedelta(days=1)
                    conditions.append(InspectionEvent.created_at >= value if lower else InspectionEvent.created_at < value)
            total = await db.scalar(select(func.count(InspectionEvent.id)).where(*conditions)) or 0
            rows = (await db.execute(select(InspectionEvent).where(*conditions).order_by(InspectionEvent.created_at.desc())
                  .offset((a["page"] - 1) * a["page_size"]).limit(a["page_size"]))).scalars().all()
            self.private_terms.update(r.name for r in rows)
            return {"total": total, "page": a["page"], "items": [event_dict(r) for r in rows]}, "巡检查询", "platform", "/platform/inspections"
        if name in {"get_inspection_summary", "get_detection_statistics", "get_environment_summary", "get_spatial_risk_summary"}:
            event = await owned_event(db, uid, a["inspection_id"])
            self.private_terms.add(event.name)
            url = f"/platform/inspections/{event.inspection_id}"
            if name == "get_environment_summary":
                data = await environment(db, event)
            elif name == "get_detection_statistics":
                data = await detections(db, event)
            elif name == "get_spatial_risk_summary":
                spatial = await task_service.spatial_result(db, uid, event.inspection_id)
                grids = sorted(spatial["risk_grids"], key=lambda g: (g["risk_level"] != "INSUFFICIENT", g["risk_score"]), reverse=True)[:a["limit"]]
                data = {"grids": [{k: g[k] for k in ("cell_id", "valid_sample_count", "suspicious_count", "risk_score", "risk_level")}
                                  | {"images": g["images"][:3]} for g in grids],
                        "risk_formula": spatial["risk_formula"], "risk_thresholds": spatial["risk_thresholds"],
                        "note": "位置无效的采样不进入分区；少于3个有效样本为数据不足"}
            else:
                data = {**event_dict(event), "detection": await detections(db, event), "environment": await environment(db, event)}
            return data, event.name + " · " + LABELS[name], "platform", url
        if name == "compare_inspections":
            first = await owned_event(db, uid, a["first_id"])
            second = await owned_event(db, uid, a["second_id"])
            if not first.field_id or first.field_id != second.field_id:
                raise BusinessError("需要同一烟田的两次巡检才能比较")
            envs = [await environment(db, r) for r in (first, second)]
            dets = [await detections(db, r) for r in (first, second)]
            rows = []
            for key in envs[0]["metrics"]:
                x, y = [e["metrics"][key]["mean"] for e in envs]
                rows.append({"metric": key + "均值", "first": x, "second": y,
                             "delta": round(y - x, 3) if x is not None and y is not None else None})
            for key in ("edge_target_count", "cloud_target_count"):
                x, y = [d[key] for d in dets]
                rows.append({"metric": key, "first": x, "second": y, "delta": y - x})
            data = {"first": event_dict(first), "second": event_dict(second), "comparison": rows,
                    "sample_counts": [e["sample_count"] for e in envs], "cloud_truncated": any(d["cloud_truncated"] for d in dets),
                    "spatially_comparable": first.field_version == second.field_version,
                    "limitations": "描述性比较；采样覆盖、模型版本未经统一。不同烟田版本不比较同编号分区；差异不代表病害发生率变化"}
            return data, "两次巡检比较", "platform", f"/platform/inspections/{second.inspection_id}"
        if name == "resolve_location":
            if a["query"].strip() not in self.location_hints:
                raise BusinessError("请先让用户明确真实天气地区，不得猜测地点或使用模拟坐标")
            data = await assistant_providers.weather_request("/geo/v2/city/lookup", {"location": a["query"], "number": 5, "lang": "zh"})
            locations = data.get("location", [])
            self.resolved_locations.extend(locations)
            return locations, "天气地点候选", "weather", None
        if name in {"get_weather", "get_weather_alerts"}:
            lat, lon = round(a["latitude"], 2), round(a["longitude"], 2)
            if not any(round(float(candidate.get("lat", 999)), 2) == lat
                       and round(float(candidate.get("lon", 999)), 2) == lon for candidate in self.resolved_locations):
                raise BusinessError("必须先解析用户明确的真实地点并使用返回坐标，不能直接猜测坐标")
            if name == "get_weather_alerts":
                data = await assistant_providers.weather_request(f"/weatheralert/v1/current/{lat}/{lon}", {"localTime": "true", "lang": "zh"})
            else:
                params = {"localTime": "true", "lang": "zh"}
                results = await asyncio.gather(
                    assistant_providers.weather_request(f"/weather/v1/current/{lat}/{lon}", params),
                    assistant_providers.weather_request(f"/weather/v1/daily/{lat}/{lon}", {**params, "days": a["days"]}),
                    assistant_providers.weather_request(f"/weather/v1/hourly/{lat}/{lon}", {**params, "hours": 24}),
                    return_exceptions=True)
                data = {key: value if isinstance(value, dict) else None
                        for key, value in zip(("current", "forecast", "hourly"), results)}
                data["errors"] = {key: "该部分暂时无法获取，不代表无风险"
                                  for key, value in zip(("current", "forecast", "hourly"), results)
                                  if isinstance(value, BaseException)}
                if all(value is None for key, value in data.items() if key != "errors"):
                    raise assistant_providers.ProviderError("天气服务暂时不可用或未配置，无法查询实时天气")
            data["location"] = {"name": a["location_name"], "latitude": lat, "longitude": lon}
            return data, a["location_name"] + " · " + LABELS[name], "weather", "https://www.qweather.com"
        if name == "search_knowledge":
            hits = await assistant_files.search(db, uid, a["query"], self.request.get("attachment_ids"))
            for hit in hits:
                hit["evidence_id"] = self.cite(hit["title"], "document", hit, hit.get("url"), page=hit["page"], locator=hit["locator"])
            return hits, "知识检索结果", "knowledge", None
        if name == "search_web":
            if not self.request.get("web_enabled"):
                raise BusinessError("本次会话已关闭联网搜索")
            if self.search_count >= 2:
                raise BusinessError("本次联网搜索已达上限")
            query = a["query"]
            # Guard names even when the model has not called a platform lookup first.
            for model in (Field, InspectionEvent):
                names = (await db.execute(select(model.name).where(model.owner_user_id == uid).limit(1000))).scalars().all()
                self.private_terms.update(names)
            if re.search(r"(?:FIELD_|INS_|TLD_|ATT_|\b\d{7,}\b|\d+\.\d{3,})", query, re.I) or any(t and t in query for t in self.private_terms):
                raise BusinessError("联网查询仅允许公共农业知识关键词，不得包含平台对象或私人数据")
            self.search_count += 1
            hits = await assistant_providers.web_search(query, a["trusted_only"])
            for hit in hits:
                hit["evidence_id"] = self.cite(hit["title"], "web", hit, hit.get("url"), published_at=hit.get("published_at"))
            return hits, "联网资料检索", "search", None
        if name == "read_authorized_image":
            if not self.request.get("image_enabled") or self.image_count >= 3:
                raise BusinessError("请先开启图片分析，且每次最多3张图片")
            image = await db.scalar(select(ImageRecord).join(InspectionRecord, InspectionRecord.id == ImageRecord.inspection_id)
                      .where(ImageRecord.image_id == a["image_id"], InspectionRecord.owner_user_id == uid))
            if not image:
                raise NotFoundError("图片不存在或无权访问")
            data = resolve_path(image.storage_key).read_bytes()
            if len(data) > 10 * 1024 * 1024:
                raise BusinessError("图片过大")
            mime = image.content_type or "image/jpeg"
            self.images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64," + base64.b64encode(data).decode()}})
            self.image_count += 1
            return {"image_id": image.image_id, "note": "图片仅供辅助观察，不自动写入检测结果"}, "巡检图片", "image", f"/platform/inspections"
        raise BusinessError("工具不可用")

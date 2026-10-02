"""GIS 地图查询、空间抽样与不规则风险区域生成。"""
from __future__ import annotations

from math import hypot
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inspection import DetectionRecord, ImageRecord, InspectionEvent, InspectionRecord


def _perpendicular_distance(point: dict, start: dict, end: dict) -> float:
    x, y, x1, y1, x2, y2 = point["lng"], point["lat"], start["lng"], start["lat"], end["lng"], end["lat"]
    if x1 == x2 and y1 == y2:
        return hypot(x - x1, y - y1)
    return abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1) / hypot(y2 - y1, x2 - x1)


def spatial_sample(points: list[dict], max_points: int = 600) -> list[dict]:
    """Douglas–Peucker 空间抽样，保留转折形态而不是按时间跳点。"""
    if len(points) <= max_points:
        return points
    tolerance = 0.000001
    result = points
    while len(result) > max_points:
        def simplify(items: list[dict]) -> list[dict]:
            if len(items) <= 2:
                return items
            distances = [_perpendicular_distance(p, items[0], items[-1]) for p in items[1:-1]]
            maximum = max(distances, default=0)
            if maximum <= tolerance:
                return [items[0], items[-1]]
            idx = distances.index(maximum) + 1
            return simplify(items[:idx + 1])[:-1] + simplify(items[idx:])
        result = simplify(points)
        tolerance *= 1.8
    return result


def _hull(points: list[tuple[float, float]]) -> list[list[float]]:
    """单调链凸包；用作相邻同风险 Voronoi 单元的连续合并外边界。"""
    pts = sorted(set(points))
    if len(pts) <= 1:
        return [[*p] for p in pts]
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [[x, y] for x, y in lower[:-1] + upper[:-1]]


def _region_polygon(points: list[dict]) -> list[list[float]]:
    coords = [(p["lng"], p["lat"]) for p in points]
    if len(coords) >= 3:
        return _hull(coords)
    pad = 0.00012
    x, y = coords[0]
    return [[x - pad, y], [x - pad / 2, y + pad], [x + pad / 2, y + pad], [x + pad, y], [x + pad / 2, y - pad], [x - pad / 2, y - pad]]


async def get_map_data(
    db: AsyncSession, user_id: int, inspection_id: Optional[str] = None
) -> dict[str, Any]:
    query = (
        select(InspectionRecord)
        .options(
            selectinload(InspectionRecord.location),
            selectinload(InspectionRecord.detection).selectinload(DetectionRecord.results),
            selectinload(InspectionRecord.images).selectinload(ImageRecord.cloud_detection),
            selectinload(InspectionRecord.event),
        )
        .where(InspectionRecord.owner_user_id == user_id)
        .order_by(InspectionRecord.device_id, InspectionRecord.captured_at)
    )
    if inspection_id:
        query = query.join(InspectionEvent, InspectionEvent.id == InspectionRecord.event_id).where(
            InspectionEvent.inspection_id == inspection_id
        )
    records = (await db.execute(query)).scalars().all()
    grouped: dict[str, list[dict]] = {}
    disease_points = []
    for r in records:
        if (not r.location or not r.location.position_valid
                or r.location.longitude is None or r.location.latitude is None):
            continue
        group_key = r.event.inspection_id if r.event else f"legacy:{r.device_id}"
        point = {"lng": r.location.longitude, "lat": r.location.latitude, "data_id": r.data_id}
        grouped.setdefault(group_key, []).append(point)
        targets = []
        if r.detection:
            targets.extend({"class": x.class_name, "confidence": x.confidence} for x in r.detection.results)
        for image in r.images:
            if image.cloud_detection and image.cloud_detection.status == "completed":
                targets.extend(image.cloud_detection.results or [])
        if targets:
            avg = sum(float(x.get("confidence", 0)) for x in targets) / len(targets)
            score = min(100, round(28 + len(targets) * 9 + avg * 42, 1))
            level = "HIGH" if score >= 70 else "MEDIUM" if score >= 38 else "LOW"
            disease_points.append({**point, "count": len(targets), "score": score, "level": level, "classes": sorted({x.get("class", "unknown") for x in targets})})
    tracks = [{"inspection_id": key, "points": spatial_sample(points)} for key, points in grouped.items()]
    # 同等级且空间邻近的点合并成连续不规则区域，单点则生成六边形 Voronoi 近似单元。
    regions = []
    remaining = disease_points[:]
    while remaining:
        seed = remaining.pop(0)
        cluster = [seed]
        changed = True
        while changed:
            changed = False
            for candidate in remaining[:]:
                if candidate["level"] == seed["level"] and any(hypot(candidate["lng"] - p["lng"], candidate["lat"] - p["lat"]) < 0.0015 for p in cluster):
                    cluster.append(candidate)
                    remaining.remove(candidate)
                    changed = True
        regions.append({
            "level": seed["level"],
            "score": round(sum(p["score"] for p in cluster) / len(cluster), 1),
            "polygon": _region_polygon(cluster),
            "point_count": len(cluster),
        })
    return {"tracks": tracks, "disease_points": disease_points, "regions": regions, "sampling": "douglas-peucker", "region_method": "voronoi-density-merge"}

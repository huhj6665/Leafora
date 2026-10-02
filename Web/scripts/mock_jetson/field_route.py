"""Deterministic in-field lawnmower route generation."""
from __future__ import annotations

import math


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside, j = False, len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _nearest_inside(x: float, y: float, polygon: list[list[float]], center: tuple[float, float]) -> tuple[float, float]:
    if point_in_polygon(x, y, polygon):
        return x, y
    cx, cy = center
    for step in range(1, 101):
        ratio = step / 100
        candidate = (x + (cx - x) * ratio, y + (cy - y) * ratio)
        if point_in_polygon(candidate[0], candidate[1], polygon):
            return candidate
    return center


def build_route(snapshot: dict, sample_count: int) -> list[dict]:
    polygon = [list(map(float, p)) for p in snapshot["pixel_boundary"]]
    if polygon[0] == polygon[-1]:
        polygon = polygon[:-1]
    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    margin_x, margin_y = (max(xs) - min(xs)) * 0.08, (max(ys) - min(ys)) * 0.08
    left, right = min(xs) + margin_x, max(xs) - margin_x
    top, bottom = min(ys) + margin_y, max(ys) - margin_y
    anchors: list[tuple[float, float]] = []
    lines = 8
    for line in range(lines):
        y = top + (bottom - top) * line / (lines - 1)
        candidates = [(left + (right - left) * i / 100, y) for i in range(101)]
        inside = [p for p in candidates if point_in_polygon(p[0], p[1], polygon)]
        if not inside:
            continue
        pair = [inside[0], inside[-1]] if line % 2 == 0 else [inside[-1], inside[0]]
        anchors.extend(pair)
    if len(anchors) < 2:
        anchors = [(cx, cy), (cx, cy)]
    lengths = [0.0]
    for a, b in zip(anchors, anchors[1:]):
        lengths.append(lengths[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = lengths[-1] or 1.0
    transform = snapshot["transform_params"]
    result = []
    for index in range(max(2, sample_count)):
        target = total * index / (max(2, sample_count) - 1)
        segment = next((i for i in range(1, len(lengths)) if lengths[i] >= target), len(lengths) - 1)
        start, end = anchors[segment - 1], anchors[segment]
        span = lengths[segment] - lengths[segment - 1] or 1.0
        ratio = (target - lengths[segment - 1]) / span
        x, y = start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio
        x, y = _nearest_inside(x, y, polygon, (cx, cy))
        lng = float(transform["origin_longitude"]) + x * float(transform["longitude_per_pixel"])
        lat = float(transform["origin_latitude"]) + y * float(transform["latitude_per_pixel"])
        heading = (math.degrees(math.atan2(end[0] - start[0], -(end[1] - start[1]))) + 360) % 360
        result.append({"x": x, "y": y, "latitude": round(lat, 8), "longitude": round(lng, 8), "heading": round(heading, 1)})
    return result

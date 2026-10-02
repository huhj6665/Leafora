"""Deterministic field-clipped Voronoi helpers without optional geometry packages."""
from __future__ import annotations

import hashlib
import json
import math
import random
from copy import deepcopy
from functools import lru_cache
from typing import Iterable


EPSILON = 1e-7


def _open_polygon(points: Iterable[Iterable[float]]) -> list[list[float]]:
    polygon = [[float(point[0]), float(point[1])] for point in points]
    if len(polygon) > 1 and polygon[0] == polygon[-1]:
        polygon.pop()
    return polygon


def polygon_area(points: Iterable[Iterable[float]]) -> float:
    polygon = _open_polygon(points)
    return abs(sum(
        polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
        for index in range(len(polygon))
    )) / 2 if len(polygon) >= 3 else 0.0


def _on_segment(x: float, y: float, first: list[float], second: list[float]) -> bool:
    cross = (x - first[0]) * (second[1] - first[1]) - (y - first[1]) * (second[0] - first[0])
    if abs(cross) > EPSILON:
        return False
    return (
        min(first[0], second[0]) - EPSILON <= x <= max(first[0], second[0]) + EPSILON
        and min(first[1], second[1]) - EPSILON <= y <= max(first[1], second[1]) + EPSILON
    )


def point_in_polygon(x: float, y: float, points: Iterable[Iterable[float]]) -> bool:
    polygon = _open_polygon(points)
    if len(polygon) < 3:
        return False
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if _on_segment(x, y, previous, current):
            return True
        if ((current[1] > y) != (previous[1] > y)):
            crossing_x = (previous[0] - current[0]) * (y - current[1]) / (
                previous[1] - current[1]
            ) + current[0]
            if x < crossing_x:
                inside = not inside
        previous = current
    return inside


def _intersection(first: list[float], second: list[float], a: float, b: float, c: float) -> list[float]:
    dx, dy = second[0] - first[0], second[1] - first[1]
    denominator = a * dx + b * dy
    if abs(denominator) <= EPSILON:
        return second[:]
    amount = (c - a * first[0] - b * first[1]) / denominator
    return [first[0] + amount * dx, first[1] + amount * dy]


def _clip_half_plane(points: list[list[float]], a: float, b: float, c: float) -> list[list[float]]:
    if not points:
        return []
    result: list[list[float]] = []
    previous = points[-1]
    previous_inside = a * previous[0] + b * previous[1] <= c + EPSILON
    for current in points:
        current_inside = a * current[0] + b * current[1] <= c + EPSILON
        if current_inside:
            if not previous_inside:
                result.append(_intersection(previous, current, a, b, c))
            result.append(current[:])
        elif previous_inside:
            result.append(_intersection(previous, current, a, b, c))
        previous, previous_inside = current, current_inside
    cleaned: list[list[float]] = []
    for point in result:
        if not cleaned or abs(point[0] - cleaned[-1][0]) > EPSILON or abs(point[1] - cleaned[-1][1]) > EPSILON:
            cleaned.append(point)
    if len(cleaned) > 1 and abs(cleaned[0][0] - cleaned[-1][0]) <= EPSILON and abs(cleaned[0][1] - cleaned[-1][1]) <= EPSILON:
        cleaned.pop()
    return cleaned


def deterministic_seeds(field_id: str, field_version: int, boundary: list, count: int = 100) -> list[list[float]]:
    polygon = _open_polygon(boundary)
    if len(polygon) < 3:
        return []
    min_x, max_x = min(p[0] for p in polygon), max(p[0] for p in polygon)
    min_y, max_y = min(p[1] for p in polygon), max(p[1] for p in polygon)
    digest = hashlib.sha256(f"{field_id}:{field_version}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    seeds: list[list[float]] = []
    aspect = max((max_x - min_x) / max(max_y - min_y, EPSILON), 0.25)
    columns = max(1, round(math.sqrt(count * aspect)))
    rows = max(1, (count + columns - 1) // columns)
    for row in range(rows):
        for column in range(columns):
            if len(seeds) >= count:
                break
            x = min_x + (column + rng.uniform(0.32, 0.68)) * (max_x - min_x) / columns
            y = min_y + (row + rng.uniform(0.32, 0.68)) * (max_y - min_y) / rows
            if point_in_polygon(x, y, polygon):
                seeds.append([x, y])
    attempts = 0
    while len(seeds) < count and attempts < count * 200:
        x, y = rng.uniform(min_x, max_x), rng.uniform(min_y, max_y)
        if point_in_polygon(x, y, polygon):
            seeds.append([x, y])
        attempts += 1
    return seeds


@lru_cache(maxsize=64)
def _cached_clipped_voronoi(
    field_id: str, field_version: int, boundary_json: str, count: int
) -> tuple[dict, ...]:
    """Cache only immutable field-version geometry, never inspection risk values."""
    polygon = json.loads(boundary_json)
    seeds = deterministic_seeds(field_id, field_version, polygon, count)
    cells: list[dict] = []
    for index, seed in enumerate(seeds):
        cell = [point[:] for point in polygon]
        for other_index, other in enumerate(seeds):
            if index == other_index:
                continue
            a, b = 2 * (other[0] - seed[0]), 2 * (other[1] - seed[1])
            c = other[0] ** 2 + other[1] ** 2 - seed[0] ** 2 - seed[1] ** 2
            cell = _clip_half_plane(cell, a, b, c)
            if len(cell) < 3:
                break
        if len(cell) >= 3 and polygon_area(cell) > EPSILON:
            cells.append({"cell_id": f"V{index + 1:03d}", "seed": seed, "polygon": cell})
    return tuple(cells)


def clipped_voronoi(field_id: str, field_version: int, boundary: list, count: int = 100) -> list[dict]:
    polygon = _open_polygon(boundary)
    # The actual boundary snapshot is part of the key. The same field/version
    # therefore cannot accidentally reuse geometry from a different snapshot.
    boundary_json = json.dumps(polygon, ensure_ascii=False, separators=(",", ":"))
    return deepcopy(list(_cached_clipped_voronoi(field_id, field_version, boundary_json, count)))


def voronoi_cache_info():
    return _cached_clipped_voronoi.cache_info()


def clear_voronoi_cache() -> None:
    _cached_clipped_voronoi.cache_clear()


def assign_cell(x: float, y: float, cells: list[dict]) -> int:
    for index, cell in enumerate(cells):
        if point_in_polygon(x, y, cell["polygon"]):
            return index
    # Floating point error on a shared edge must not drop a sample.
    return min(
        range(len(cells)),
        key=lambda index: (x - cells[index]["seed"][0]) ** 2 + (y - cells[index]["seed"][1]) ** 2,
    )

"""Deterministic clipped Voronoi risk partition tests."""
from app.services import voronoi_service


BOUNDARY = [
    [203, 548], [252, 523], [438, 501], [492, 500], [525, 526],
    [773, 553], [999, 579], [1041, 704], [1078, 858], [1118, 1097],
    [137, 1097], [132, 1015], [148, 875], [166, 733], [181, 632], [203, 548],
]


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _self_intersects(polygon):
    count = len(polygon)
    for first in range(count):
        a, b = polygon[first], polygon[(first + 1) % count]
        for second in range(first + 1, count):
            if second in {first, (first + 1) % count} or (second + 1) % count in {first, (first + 1) % count}:
                continue
            c, d = polygon[second], polygon[(second + 1) % count]
            if _orientation(a, b, c) * _orientation(a, b, d) < 0 and _orientation(c, d, a) * _orientation(c, d, b) < 0:
                return True
    return False


def test_voronoi_is_deterministic_clipped_and_covers_field():
    first = voronoi_service.clipped_voronoi("FIELD_A01", 2, BOUNDARY)
    second = voronoi_service.clipped_voronoi("FIELD_A01", 2, BOUNDARY)
    assert first == second
    assert len(first) == 100
    assert all(len(cell["polygon"]) >= 3 for cell in first)
    assert all(not _self_intersects(cell["polygon"]) for cell in first)
    assert all(
        voronoi_service.point_in_polygon(point[0], point[1], BOUNDARY)
        for cell in first for point in cell["polygon"]
    )
    field_area = voronoi_service.polygon_area(BOUNDARY)
    cells_area = sum(voronoi_service.polygon_area(cell["polygon"]) for cell in first)
    assert cells_area / field_area > 0.995
    assert cells_area / field_area < 1.005


def test_same_field_version_is_comparable_and_sample_assignment_is_stable():
    first_task = voronoi_service.clipped_voronoi("FIELD_A01", 2, BOUNDARY)
    another_task = voronoi_service.clipped_voronoi("FIELD_A01", 2, BOUNDARY)
    next_version = voronoi_service.clipped_voronoi("FIELD_A01", 3, BOUNDARY)
    assert [cell["polygon"] for cell in first_task] == [cell["polygon"] for cell in another_task]
    assert [cell["seed"] for cell in first_task] != [cell["seed"] for cell in next_version]
    for index, cell in enumerate(first_task):
        assert voronoi_service.assign_cell(*cell["seed"], first_task) == index


def test_boundary_rounding_falls_back_to_nearest_seed():
    cells = voronoi_service.clipped_voronoi("FIELD_A01", 2, BOUNDARY)
    index = voronoi_service.assign_cell(203.0 - 1e-6, 548.0, cells)
    assert 0 <= index < len(cells)


def test_cache_reuses_exact_snapshot_but_not_changed_boundary():
    voronoi_service.clear_voronoi_cache()
    first = voronoi_service.clipped_voronoi("FIELD_A01", 2, BOUNDARY)
    before = voronoi_service.voronoi_cache_info()
    second = voronoi_service.clipped_voronoi("FIELD_A01", 2, BOUNDARY)
    after = voronoi_service.voronoi_cache_info()
    changed = [point[:] for point in BOUNDARY]
    changed[1][0] += 0.5
    third = voronoi_service.clipped_voronoi("FIELD_A01", 2, changed)

    assert first == second
    assert after.hits == before.hits + 1
    assert third != first
    assert voronoi_service.voronoi_cache_info().misses == after.misses + 1

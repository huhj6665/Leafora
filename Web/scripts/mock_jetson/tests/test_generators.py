from pathlib import Path

from scripts.mock_jetson.config import MockConfig, load_config
from scripts.mock_jetson.generators import DataBuilder, DiseaseGenerator, EnvironmentGenerator, GPSGenerator
from scripts.mock_jetson.simulator import ImageCatalog, SimulatorState, VirtualJetsonSimulator
from scripts.mock_jetson.outbox import PersistentOutbox
from scripts.mock_jetson.field_route import build_route, point_in_polygon


def config(**kwargs):
    base = dict(
        start_lat=39.0, start_lon=117.0, end_lat=39.001, end_lon=117.001,
        speed_mps=1.5, sample_interval=2.0, route_curve_m=8.0,
        disease_cluster_count=2, disease_sigma_m=20.0, disease_rate=0.9,
        random_seed=42,
    )
    base.update(kwargs)
    return MockConfig(**base)


def test_load_config_reads_simulator_env_and_process_env_wins(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MOCK_DEVICE_ID=from-file\nMOCK_DEVICE_SECRET=file-secret\nMOCK_HTTP_DEBUG=false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MOCK_DEVICE_ID", "from-process")
    monkeypatch.delenv("MOCK_DEVICE_SECRET", raising=False)
    monkeypatch.delenv("MOCK_HTTP_DEBUG", raising=False)

    loaded = load_config(env_file)

    assert loaded.device_id == "from-process"
    assert loaded.device_secret == "file-secret"
    assert loaded.http_debug is False


def test_gps_follows_route_and_reaches_endpoints():
    gps = GPSGenerator(config())
    count = gps.recommended_samples
    first, middle, last = gps.generate(0, count), gps.generate(count // 2, count), gps.generate(count - 1, count)
    assert (first["latitude"], first["longitude"]) == (39.0, 117.0)
    assert (last["latitude"], last["longitude"]) == (39.001, 117.001)
    assert middle["latitude"] > first["latitude"]
    assert first["ground_speed_mps"] == 1.5
    assert last["ground_speed_mps"] == 0.0


def test_environment_changes_smoothly():
    gen = EnvironmentGenerator(42)
    rows = [gen.generate(i * 2, f"2026-09-24T00:00:{i:02d}Z") for i in range(10)]
    assert max(abs(rows[i]["temperature"] - rows[i - 1]["temperature"]) for i in range(1, len(rows))) < 1.0
    assert max(abs(rows[i]["humidity"] - rows[i - 1]["humidity"]) for i in range(1, len(rows))) < 2.0


def test_disease_probability_is_spatially_clustered():
    cfg = config()
    gps = GPSGenerator(cfg)
    disease = DiseaseGenerator(cfg, gps)
    center = disease.centers[0]
    near = disease.probability(center.latitude, center.longitude)
    far = disease.probability(cfg.start_lat - 0.01, cfg.start_lon - 0.01)
    assert near > 0.85
    assert far < 0.05


def test_data_builder_has_required_binding_and_no_forged_user():
    builder = DataBuilder(config())
    built = builder.build("INS_UNIT_001", 0, 4, "2026-09-24T00:00:00Z", data_id="data-unit-1")
    assert built.payload["inspection_id"] == "INS_UNIT_001"
    assert built.payload["data_id"] == "data-unit-1"
    assert built.payload["timestamp"] == built.payload["environment"]["sampled_at"]
    assert "user_id" not in built.payload
    assert "storage_usage" in built.payload["device_status"]
    assert built.payload["schema_version"] == "1.2"
    assert built.payload["sequence"] == 0
    assert built.payload["location"]["sampled_at"] == built.payload["timestamp"]
    assert built.payload["environment"]["valid"] is True


def test_image_catalog_separates_disease_and_normal(tmp_path: Path):
    disease_dir, normal_dir = tmp_path / "disease", tmp_path / "normal"
    disease_dir.mkdir(); normal_dir.mkdir()
    (disease_dir / "d.jpg").write_bytes(b"d")
    (normal_dir / "n.jpg").write_bytes(b"n")
    catalog = ImageCatalog(config(disease_images_dir=str(disease_dir), normal_images_dir=str(normal_dir), test_images_dir=str(tmp_path / "none")))
    assert catalog.select(True, 0).name == "d.jpg"
    assert catalog.select(False, 0).name == "n.jpg"


def test_dry_run_completes_lifecycle(capsys):
    simulator = VirtualJetsonSimulator(config())
    stats = simulator.run(samples=5, dry_run=True, upload_images=False, inspection_id="INS_DRY_001")
    output = capsys.readouterr().out
    assert '"command": "START"' in output
    assert '"command": "END"' in output
    assert '"request_id": "REQ_' in output
    assert stats.samples == 5
    assert simulator.state == SimulatorState.COMPLETED


def test_normative_virtual_device_default():
    assert MockConfig().device_id == "TLD_JETSON_001"


def test_persistent_outbox_reuses_business_ids_and_survives_restart(tmp_path: Path):
    path = tmp_path / "outbox.sqlite3"
    payload = {"device_id": "TLD_JETSON_001", "data_id": "DATA_FIXED_001"}
    with PersistentOutbox(path) as outbox:
        assert outbox.enqueue("data", "DATA_FIXED_001", payload) is True
        assert outbox.enqueue("data", "DATA_FIXED_001", payload) is False
        assert outbox.count() == 1

    with PersistentOutbox(path) as reopened:
        items = reopened.items()
        assert len(items) == 1
        assert items[0].business_id == "DATA_FIXED_001"
        assert items[0].payload == payload
        reopened.acknowledge(items[0].kind, items[0].business_id)
        assert reopened.count() == 0


def field_snapshot():
    return {
        "field_id": "FIELD_A01", "version": 1,
        "pixel_boundary": [[100, 100], [900, 100], [900, 700], [100, 700], [100, 100]],
        "transform_params": {"image_width": 1000, "image_height": 800,
                             "origin_longitude": 113.0, "origin_latitude": 23.5,
                             "longitude_per_pixel": .000001, "latitude_per_pixel": -.000001},
    }


def test_field_route_is_deterministic_and_clipped_inside_boundary():
    first = build_route(field_snapshot(), 90)
    second = build_route(field_snapshot(), 90)
    assert first == second
    polygon = field_snapshot()["pixel_boundary"][:-1]
    assert all(point_in_polygon(point["x"], point["y"], polygon) for point in first)


def test_downlink_start_end_ack_and_v13_payload_are_idempotent():
    simulator = VirtualJetsonSimulator(config(device_id="TLD_JETSON_001"))
    start = {"type": "inspection_command", "command_id": "CMD_START_1", "command": "START_INSPECTION",
             "inspection_id": "INS_CLOUD_1", "device_id": "TLD_JETSON_001", "field_id": "FIELD_A01",
             "field_version": 1, "field_snapshot": field_snapshot(), "run_mode": "FAST_TEST"}
    accepted = simulator.accept_command(start)
    assert accepted["status"] == "ACCEPTED"
    assert simulator.accept_command(start) == accepted
    sample = simulator.next_sample().payload
    assert sample["schema_version"] == "1.3"
    assert sample["field_id"] == "FIELD_A01"
    assert sample["data_provenance"] == "SIMULATED"
    end = {"type": "inspection_command", "command_id": "CMD_END_1", "command": "END_INSPECTION",
           "inspection_id": "INS_CLOUD_1", "device_id": "TLD_JETSON_001"}
    assert simulator.accept_command(end)["phase"] == "SYNCING"
    assert simulator.next_sample() is None

"""Durable two-stage END and task-scoped business outbox accounting."""
import pytest

from scripts.mock_jetson.outbox import OutboxItem, PersistentOutbox
from scripts.mock_jetson.simulator import SimulatorState, VirtualJetsonSimulator
from scripts.mock_jetson.tests.test_generators import config, field_snapshot


def start_command():
    return {"type": "inspection_command", "command_id": "CMD_START_DURABLE", "command": "START_INSPECTION",
            "inspection_id": "INS_DURABLE", "device_id": "TLD_JETSON_001", "field_id": "FIELD_A01",
            "field_version": 1, "field_snapshot": field_snapshot(), "run_mode": "FAST_TEST"}


def end_command():
    return {"type": "inspection_command", "command_id": "CMD_END_DURABLE", "command": "END_INSPECTION",
            "inspection_id": "INS_DURABLE", "device_id": "TLD_JETSON_001"}


class Broker:
    def __init__(self):
        self.data, self.acks = [], []

    def publish_data(self, payload):
        self.data.append(payload)
        return True

    def publish_ack(self, payload):
        self.acks.append(payload)
        return True


def test_restart_preserves_stop_summary_final_and_original_ids(tmp_path):
    cfg = config(outbox_path=str(tmp_path / "outbox.sqlite3"))
    simulator = VirtualJetsonSimulator(cfg)
    broker = Broker()
    with PersistentOutbox(cfg.outbox_path) as outbox:
        simulator.accept_command(start_command())
        built = simulator.next_sample()
        simulator._checkpoint(outbox, [OutboxItem("data", built.payload["data_id"], built.payload)])
        accepted = simulator.accept_command(end_command(), outbox.business_count("INS_DURABLE"))
        simulator._checkpoint(outbox, [simulator._ack_item(accepted)])
        assert accepted["summary"]["sample_count"] == 1
        assert accepted["summary"]["last_sequence"] == 0
        assert outbox.count() == 2 and outbox.business_count("INS_DURABLE") == 1
        assert simulator._finish_end(outbox) is False

    recovered = VirtualJetsonSimulator(cfg)
    with PersistentOutbox(cfg.outbox_path) as outbox:
        recovered._restore(outbox)
        assert recovered.state == SimulatorState.SYNCING and recovered.index == 1
        assert recovered.next_sample() is None
        assert recovered.accept_command({**end_command(), "expires_at": "2020-01-01T00:00:00Z"}) == accepted
        recovered._flush(broker, outbox)
        assert broker.data == [built.payload]
        assert recovered._finish_end(outbox) is True
        recovered._flush(broker, outbox)
        final = broker.acks[-1]
        assert final["status"] == final["phase"] == "COMPLETED"
        assert final["command_id"] == accepted["command_id"]
        assert final["summary"] == {**accepted["summary"], "pending_sync_count": 0}

    # Even PUBACKed receipts remain replayable after a second restart.
    again = VirtualJetsonSimulator(cfg)
    with PersistentOutbox(cfg.outbox_path) as outbox:
        again._restore(outbox)
        again._requeue_end_receipts(outbox)
        phases = [item.payload["status"] for item in outbox.items() if item.kind == "ack"]
        assert phases == ["ACCEPTED", "COMPLETED"]
        assert outbox.business_count("INS_DURABLE") == 0
        assert again.state == SimulatorState.STANDBY


def test_zero_sample_end_and_pending_image_block_final(tmp_path):
    simulator = VirtualJetsonSimulator(config(outbox_path=str(tmp_path / "outbox.sqlite3")))
    with PersistentOutbox(simulator.config.outbox_path) as outbox:
        simulator.accept_command(start_command())
        accepted = simulator.accept_command(end_command(), 1)
        simulator._checkpoint(outbox, [OutboxItem("image", "IMG_FAILED", {"inspection_id": "INS_DURABLE"})])
        assert accepted["summary"]["last_data_id"] is accepted["summary"]["last_sequence"] is None
        assert accepted["summary"]["sample_count"] == 0
        assert simulator._finish_end(outbox) is False
        # Only an actual successful image acknowledgment may clear the item.
        outbox.acknowledge("image", "IMG_FAILED")
        assert simulator._finish_end(outbox) is True
        assert simulator.final_ack_cache["CMD_END_DURABLE"]["summary"]["sample_count"] == 0


def test_running_checkpoint_and_expired_cached_start_are_idempotent(tmp_path):
    cfg = config(outbox_path=str(tmp_path / "outbox.sqlite3"))
    original = VirtualJetsonSimulator(cfg)
    with PersistentOutbox(cfg.outbox_path) as outbox:
        ack = original.accept_command(start_command())
        built = original.next_sample()
        original._checkpoint(outbox, [OutboxItem("data", built.payload["data_id"], built.payload)])
    recovered = VirtualJetsonSimulator(cfg)
    with PersistentOutbox(cfg.outbox_path) as outbox:
        recovered._restore(outbox)
        assert recovered.accept_command({**start_command(), "expires_at": "2020-01-01T00:00:00Z"}) == ack
        assert recovered.next_sample().payload["sequence"] == 1
        assert outbox.items()[0].payload == built.payload


def test_legacy_outbox_is_preserved_not_recounted_or_deleted(tmp_path):
    cfg = config(outbox_path=str(tmp_path / "outbox.sqlite3"))
    simulator = VirtualJetsonSimulator(cfg)
    with PersistentOutbox(cfg.outbox_path) as outbox:
        outbox.enqueue("data", "DATA_OLD", {"inspection_id": "INS_OLD"})
        with pytest.raises(RuntimeError, match="Legacy outbox"):
            simulator._restore(outbox)
        assert outbox.count() == 1

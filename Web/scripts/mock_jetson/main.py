"""Virtual Jetson Simulator V3 下行命令监听入口。"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.mock_jetson.config import load_config
from scripts.mock_jetson.simulator import VirtualJetsonSimulator


def main() -> None:
    parser = argparse.ArgumentParser(description="TLD Virtual Jetson Simulator V3（云端下行驱动）")
    parser.add_argument("--mode", choices=["FAST_TEST", "REALTIME_SIMULATION"], default="FAST_TEST", help="仅影响 dry-run；正式运行服从云端 START 命令")
    parser.add_argument("--samples", type=int, default=None, help="仅用于 dry-run 的预览采样数")
    parser.add_argument("--inspection-id", default=None, help="仅用于 dry-run 的预览任务 ID")
    parser.add_argument("--dry-run", action="store_true", help="不连接 MQTT/HTTP，模拟收到云端 START/END")
    parser.add_argument("--seed", type=int, default=None, help="覆盖确定性随机种子")
    args = parser.parse_args()

    config = load_config()
    if args.seed is not None:
        config.random_seed = args.seed
    simulator = VirtualJetsonSimulator(config)
    stats = simulator.run(
        mode=args.mode,
        samples=args.samples,
        upload_images=True,
        dry_run=args.dry_run,
        bind_owner=False,
        inspection_id=args.inspection_id,
    )
    print("\n=== Virtual Jetson V3 Summary ===")
    print(f"inspection_id: {stats.inspection_id}")
    print(f"state: {simulator.state.value}")
    print(f"samples: {stats.samples}")
    print(f"mqtt_published: {stats.mqtt_published}")
    print(f"disease_samples: {stats.disease_samples}")
    print(f"images_uploaded: {stats.images_uploaded}/{stats.images_attempted}")
    print(f"cloud_completed: {stats.cloud_completed}")
    print(f"failed: {stats.failed}")


if __name__ == "__main__":
    main()

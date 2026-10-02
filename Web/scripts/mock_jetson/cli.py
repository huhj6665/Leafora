"""模拟 Jetson CLI.

用法示例：
    python cli.py preview --count 3
    python cli.py publish --count 1000 --mode fast
    python cli.py publish --count 100 --interval 0.1
    python cli.py publish --continuous
    python cli.py benchmark --count 10000
    python cli.py upload-images --count 1
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

# 使 `python cli.py`（从本目录运行）或 `python scripts/mock_jetson/cli.py`（从仓库根运行）均可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.mock_jetson.config import load_config
from scripts.mock_jetson.data_generator import DataGenerator
from scripts.mock_jetson.generate_preview import preview
from scripts.mock_jetson.image_uploader import ImageUploader
from scripts.mock_jetson.mqtt_publisher import MQTTPublisher

_IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def cmd_preview(args) -> None:
    print(preview(load_config(), args.count))


def cmd_publish(args) -> None:
    config = load_config()
    interval = 0.0 if args.mode == "fast" else args.interval
    publisher = MQTTPublisher(config)
    stats = publisher.publish(
        count=args.count,
        interval=interval,
        disease_rate=args.disease_rate,
        continuous=args.continuous,
    )
    print(stats.report(title=f"[publish] device={config.device_id} mode={args.mode}"))


def cmd_benchmark(args) -> None:
    """压力测试：整条数据接收能力（MQTT 侧）.

    MQTT publish 成功 ≠ 数据库已写入；最终入库数需通过后端统计/Web 查询确认。
    """
    config = load_config()
    publisher = MQTTPublisher(config)
    stats = publisher.publish(count=args.count, interval=0.0, disease_rate=args.disease_rate)
    print(stats.report(title=f"[benchmark] device={config.device_id}"))
    print("注意：以上为 MQTT 发布侧统计；数据库实际入库数请通过后端 /api/inspection/stats 确认。")


def cmd_upload_images(args) -> None:
    """每张图片 → 生成 data_id → MQTT 巡检 JSON → HTTP 上传图片 → 记录云端推理状态."""
    config = load_config()
    if args.device_id:
        config.device_id = args.device_id
    if args.images_dir:
        config.test_images_dir = args.images_dir
    if args.backend_url:
        config.backend_base_url = args.backend_url
    # 图片触发上传场景：默认模拟 Jetson 已检出目标（边缘检测为模拟数据，非云端结果）
    config.disease_rate = args.disease_rate if args.disease_rate is not None else 1.0

    img_dir = Path(config.test_images_dir)
    images = sorted([p for p in img_dir.iterdir() if p.suffix.lower() in _IMAGE_EXTS]) \
        if img_dir.is_dir() else []
    if not images:
        print(f"[失败] 目录 {img_dir} 中未找到 JPG/PNG 图片，请先放入测试图片。")
        return
    if args.count is not None:
        images = images[: args.count]

    generator = DataGenerator(config)
    publisher = MQTTPublisher(config)
    uploader = ImageUploader(config)

    summary = {
        "total": len(images),
        "mqtt_published": 0,
        "http_uploaded": 0,
        "cloud_completed": 0,
        "cloud_model_unavailable": 0,
        "cloud_failed": 0,
        "failed": 0,
    }

    for idx, image_path in enumerate(images, start=1):
        data_id = uuid.uuid4().hex
        image_id = uuid.uuid4().hex

        # 1. 构造模拟巡检 JSON（同一 data_id 用于图片关联）
        payload = generator.generate(data_id=data_id)

        # 2. 发布 MQTT（QoS1，等待 PUBACK）
        mqtt_stats = publisher.publish_payloads([payload])
        mqtt_ok = mqtt_stats.published >= 1
        if mqtt_ok:
            summary["mqtt_published"] += 1

        # 3. HTTP 上传图片（有界重试，等待 MQTT 记录入库）
        up = uploader.upload(data_id, image_id, image_path)
        http_ok = up["http_status"] == 200

        cloud_status = None
        if http_ok:
            summary["http_uploaded"] += 1
            cloud_status = (up["body"].get("data", {}) or {}).get("cloud_detection", {}).get("status")
            if cloud_status == "completed":
                summary["cloud_completed"] += 1
            elif cloud_status == "model_unavailable":
                summary["cloud_model_unavailable"] += 1
            elif cloud_status == "failed":
                summary["cloud_failed"] += 1
        else:
            summary["failed"] += 1

        line = (
            f"[{idx}/{len(images)}] {image_path.name}\n"
            f"  data_id={data_id} image_id={image_id}\n"
            f"  MQTT={'published' if mqtt_ok else 'FAILED'}"
            f"  HTTP={up['http_status']}({'uploaded' if http_ok else 'FAILED'})"
            f"  cloud={cloud_status or '—'}"
        )
        print(line)

    print("——")
    print(
        f"合计：图片 {summary['total']} | MQTT发布 {summary['mqtt_published']} | "
        f"HTTP上传 {summary['http_uploaded']} | 推理完成 {summary['cloud_completed']} | "
        f"模型不可用 {summary['cloud_model_unavailable']} | 失败 {summary['failed']}"
    )
    print("说明：MQTT 发布确认 ≠ 数据库入库；最终入库/图片关联数以后端 /api/inspection/stats 与网页查询为准。")


def main() -> None:
    parser = argparse.ArgumentParser(description="TLD 模拟 Jetson 工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prev = sub.add_parser("preview", help="生成并打印 JSON 预览")
    p_prev.add_argument("--count", type=int, default=1)
    p_prev.set_defaults(func=cmd_preview)

    p_pub = sub.add_parser("publish", help="发布 MQTT 数据")
    p_pub.add_argument("--count", type=int, default=None, help="消息数量（必须显式指定）")
    p_pub.add_argument("--mode", choices=["fast", "normal"], default="fast")
    p_pub.add_argument("--interval", type=float, default=0.1, help="normal 模式每条间隔秒")
    p_pub.add_argument("--disease-rate", type=float, default=None, help="模拟病害出现概率 0~1")
    p_pub.add_argument("--continuous", action="store_true", help="无限发送（Ctrl+C 退出）")
    p_pub.set_defaults(func=cmd_publish)

    p_bench = sub.add_parser("benchmark", help="压力测试")
    p_bench.add_argument("--count", type=int, required=True)
    p_bench.add_argument("--disease-rate", type=float, default=None)
    p_bench.set_defaults(func=cmd_benchmark)

    p_up = sub.add_parser("upload-images", help="图片触发上传：MQTT 记录 + HTTP 图片 + 云端推理")
    p_up.add_argument("--device-id", default=None, help="设备编号（默认 TLD_JETSON_001）")
    p_up.add_argument("--images-dir", default=None, help="测试图片目录")
    p_up.add_argument("--count", type=int, default=None, help="上传图片数量（默认全部）")
    p_up.add_argument("--backend-url", default=None, help="TLD 后端 HTTP 地址（默认 http://127.0.0.1:8000/api）")
    p_up.add_argument("--disease-rate", type=float, default=None, help="模拟边缘检出概率（默认 1.0）")
    p_up.set_defaults(func=cmd_upload_images)

    args = parser.parse_args()

    if args.command == "publish" and args.count is None and not args.continuous:
        parser.error("publish 必须指定 --count，或使用 --continuous 显式进入无限模式")

    args.func(args)


if __name__ == "__main__":
    main()

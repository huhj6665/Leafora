"""批量图片推理 CLI（独立测试，不依赖 PostgreSQL）.

用法（在 model_service 目录）：
    python -m app.cli --input test_images/incoming --output outputs/annotated

读取目录内 JPG/PNG，逐张推理，输出标注图到 output 目录，并打印 JSON 结果。
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from app import inference
from app.service import predict_from_bytes


def _iter_images(input_dir: Path):
    for ext in ("*.jpg", "*.jpeg", "*.png"):
        for p in sorted(input_dir.glob(ext)):
            yield p


def main() -> None:
    parser = argparse.ArgumentParser(description="RT-DETR-L 批量图片推理")
    parser.add_argument("--input", default="test_images/incoming")
    parser.add_argument("--output", default="outputs/annotated")
    args = parser.parse_args()

    if not inference.is_ready():
        raise SystemExit(f"模型未就绪：{inference.load_error()}")

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    for img_path in _iter_images(input_dir):
        result = predict_from_bytes(img_path.read_bytes())
        print(f"{img_path.name}: has_target={result.has_target} "
              f"results={[r['class'] for r in result.results]}")

        if result.annotated_image_base64:
            out_path = output_dir / f"{img_path.stem}_annotated.jpg"
            out_path.write_bytes(base64.b64decode(result.annotated_image_base64))
            print(f"  -> {out_path}")

        print(json.dumps({
            "model_name": result.model_name,
            "model_version": result.model_version,
            "weights_identifier": result.weights_identifier,
            "has_target": result.has_target,
            "results": result.results,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()

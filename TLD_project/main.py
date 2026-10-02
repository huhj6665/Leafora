# -*- coding: utf-8 -*-
"""TLD 真实 Jetson 唯一入口：默认安全的命令行通信配置模式。"""

import argparse
import os
import sys


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def build_parser():
    parser = argparse.ArgumentParser(description="TLD Jetson edge runtime")
    parser.add_argument("--cli", action="store_true", help="兼容参数；命令行现已是默认入口")
    parser.add_argument("--hardware", action="store_true", help="网络向导通过后启动硬件（桌面采集实机验收）")
    parser.add_argument("--ui", action="store_true", help="保留参数；Tkinter 联调暂停，当前不启动")
    parser.add_argument("--config", default=None, help="本地 device.env 路径")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.ui:
        print("Tkinter 联调暂停。请使用 python3 main.py 或 python3 main.py --hardware。")
        return 2
    from edge.runtime import EdgeRuntime
    runtime = EdgeRuntime(ROOT_DIR, config_path=args.config)
    from edge.cli import run_cli
    run_cli(runtime, start_hardware=args.hardware)
    return 0


if __name__ == "__main__":
    sys.exit(main())

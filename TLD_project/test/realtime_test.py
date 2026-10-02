# -*- coding: utf-8 -*-
"""
实时测试程序
============

完整视频链路：:

    摄像头 -> OpenCV -> InferenceEngine.infer() -> Detection 结果 -> 绘制 -> 显示

运行::

    python3 test/realtime_test.py

退出：按 q
"""

import os
import sys
import time

# 将项目根目录加入搜索路径，保证相对路径导入可用
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import cv2

from camera.camera import Camera
from inference.inference_engine import InferenceEngine
from inference.yolov11_postprocess import CLASS_COLORS

# 窗口名称
WINDOW_NAME = "TLD Vision Test"


def draw_detections(frame, detections):
    """在图像上绘制检测框、类别名称与置信度。"""
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det.bbox]
        color = CLASS_COLORS.get(det.class_id, (255, 255, 255))

        # 检测框
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # 标签：类别名称 + 置信度
        label = "{} {:.2f}".format(det.class_name, det.confidence)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - th - 4), (x1 + tw, y1), color, -1)
        cv2.putText(frame, label, (x1, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    return frame


def draw_fps(frame, fps):
    """在左上角显示 FPS。"""
    text = "FPS: {:.1f}".format(fps)
    cv2.putText(frame, text, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
    return frame


def run():
    """实时测试主流程。"""
    # 1. 创建摄像头与推理引擎
    camera = Camera(device="/dev/video0", width=640, height=640, fps=30)
    engine = InferenceEngine(
        model_path="models/train_best.engine",  # 预留路径，当前不依赖该文件
        conf_threshold=0.25,
        iou_threshold=0.45,
    )

    # 2. 打开摄像头
    try:
        camera.open()
        print("[INFO] 摄像头已打开: {}x{} @ {}fps".format(
            camera.width, camera.height, camera.fps))
    except Exception as e:
        print("[ERROR] 摄像头打开失败: {}".format(e))
        return

    # 提示引擎状态
    if not engine.is_loaded:
        print("[INFO] 推理引擎尚未加载（当前阶段未接入 TensorRT），仅显示原始视频画面")

    # FPS 统计
    fps = 0.0
    last_time = time.time()
    frame_count = 0

    print("[INFO] 按 q 键退出")

    # 3. 循环读取与推理
    while True:
        frame = camera.read()
        if frame is None:
            print("[WARN] 读取帧失败，退出")
            break

        # 4. 调用推理接口（当前返回空列表）
        detections = engine.infer(frame)

        # 5. 绘制检测框
        frame = draw_detections(frame, detections)

        # 6. 计算并显示 FPS
        frame_count += 1
        now = time.time()
        dt = now - last_time
        if dt >= 1.0:
            fps = frame_count / dt
            frame_count = 0
            last_time = now
        frame = draw_fps(frame, fps)

        # 7. 显示
        cv2.imshow(WINDOW_NAME, frame)

        # 8. 按 q 退出
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # 释放资源
    camera.release()
    cv2.destroyAllWindows()
    print("[INFO] 程序退出")


if __name__ == "__main__":
    run()

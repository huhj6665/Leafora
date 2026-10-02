# -*- coding: utf-8 -*-
"""
YOLO11 后处理模块
================

将模型原始输出解析为统一的 Detection 结果：:

    {
        "class_id":   0,
        "class_name": "Frogeye",
        "confidence": 0.95,
        "bbox":       [x1, y1, x2, y2],
    }

输入为 TensorRT 输出 ``(1, 8, 8400)``：8 = 4(bbox) + 4(类别)，8400 = 预测框数量。
"""

import numpy as np


# ----------------------------------------------------------------------
# 类别映射：class_id -> 类别名称
# ----------------------------------------------------------------------
CLASS_NAMES = {
    0: "Frogeye",
    1: "Mosaic",
    2: "Budworm damage",
    3: "Wildfire",
}

# 类别对应的显示颜色（BGR），用于绘制检测框
CLASS_COLORS = {
    0: (0, 255, 0),      # Frogeye         - 绿色
    1: (0, 255, 255),    # Mosaic          - 黄色
    2: (255, 0, 0),      # Budworm damage  - 蓝色
    3: (0, 0, 255),      # Wildfire        - 红色
}


class Detection:
    """单个检测结果。"""

    def __init__(self, class_id, class_name, confidence, bbox):
        """
        :param class_id:   类别索引
        :param class_name: 类别名称
        :param confidence: 置信度
        :param bbox:       边界框 [x1, y1, x2, y2]
        """
        self.class_id = int(class_id)
        self.class_name = class_name
        self.confidence = float(confidence)
        self.bbox = [float(v) for v in bbox]  # [x1, y1, x2, y2]

    def to_dict(self):
        """转换为字典格式（便于后续 MQTT / HTTP 序列化）。"""
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": self.bbox,
        }

    def __repr__(self):
        return "Detection(class_id={}, class_name={}, confidence={:.2f}, bbox={})".format(
            self.class_id, self.class_name, self.confidence, self.bbox
        )


# ----------------------------------------------------------------------
# 类别映射接口
# ----------------------------------------------------------------------
def get_class_name(class_id):
    """根据类别索引返回类别名称，未知类别返回 'unknown'。"""
    return CLASS_NAMES.get(int(class_id), "unknown")


# ----------------------------------------------------------------------
# bbox 格式转换接口
# ----------------------------------------------------------------------
def xywh_to_xyxy(bbox):
    """
    将 [cx, cy, w, h]（中心点 + 宽高）转换为 [x1, y1, x2, y2]（左上 + 右下）。

    :param bbox: [cx, cy, w, h]
    :return: [x1, y1, x2, y2]
    """
    cx, cy, w, h = bbox
    x1 = cx - w / 2.0
    y1 = cy - h / 2.0
    x2 = cx + w / 2.0
    y2 = cy + h / 2.0
    return [x1, y1, x2, y2]


def xyxy_to_xywh(bbox):
    """
    将 [x1, y1, x2, y2] 转换为 [cx, cy, w, h]。

    :param bbox: [x1, y1, x2, y2]
    :return: [cx, cy, w, h]
    """
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    w = x2 - x1
    h = y2 - y1
    return [cx, cy, w, h]


def clip_bbox(bbox, img_width, img_height):
    """
    将边界框裁剪到图像范围内。

    :param bbox: [x1, y1, x2, y2]
    :return: 裁剪后的 [x1, y1, x2, y2]
    """
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, img_width))
    y1 = max(0, min(y1, img_height))
    x2 = max(0, min(x2, img_width))
    y2 = max(0, min(y2, img_height))
    return [x1, y1, x2, y2]


# ----------------------------------------------------------------------
# NMS 接口（纯 numpy 实现，避免对 OpenCV 版本差异的依赖）
# ----------------------------------------------------------------------
def nms(detections, iou_threshold=0.45):
    """
    非极大值抑制，去除重叠的重复检测框。

    :param detections:    list[Detection]，bbox 为 [x1, y1, x2, y2]
    :param iou_threshold: IoU 阈值，重叠超过该值则保留置信度更高者
    :return: 保留的检测结果列表
    """
    if not detections:
        return []

    boxes = np.array([d.bbox for d in detections], dtype=np.float32)
    scores = np.array([d.confidence for d in detections], dtype=np.float32)

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)

    # 按置信度从高到低排序
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)

        # 计算当前框与剩余框的交并比 IoU
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter)

        # 保留 IoU 小于等于阈值的框
        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]

    return [detections[i] for i in keep]


# ----------------------------------------------------------------------
# bbox 坐标缩放接口
# ----------------------------------------------------------------------
def scale_detections(detections, img_width, img_height):
    """
    将归一化坐标 [0, 1] 的检测框缩放到图像像素坐标。

    YOLO11 输出的 bbox 为归一化坐标（相对 640x640 输入），
    本函数将其映射回原始图像尺寸。

    :param detections: list[Detection]，bbox 为归一化 [x1, y1, x2, y2]
    :param img_width:  原始图像宽度
    :param img_height: 原始图像高度
    :return: bbox 已转换为像素坐标的 Detection 列表
    """
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        det.bbox = [
            x1 * img_width,
            y1 * img_height,
            x2 * img_width,
            y2 * img_height,
        ]
    return detections


# ----------------------------------------------------------------------
# 统一后处理入口
# ----------------------------------------------------------------------
def decode_output(output, conf_threshold=0.25, iou_threshold=0.45):
    """
    解析 YOLO11 模型原始输出，生成 Detection 列表。

    YOLO11 原始输出格式：[1, 4 + num_classes, num_boxes]
      - 前 4 行：cx, cy, w, h（归一化）
      - 后 num_classes 行：各类别置信度

    :param output:         模型原始输出 (numpy.ndarray)
    :param conf_threshold: 置信度阈值
    :param iou_threshold:  NMS IoU 阈值
    :return: list[Detection]
    """
    # 去掉 batch 维度，转置为 [num_boxes, 4 + num_classes]
    preds = np.squeeze(np.array(output, dtype=np.float32)).T

    if preds.ndim == 1:
        preds = preds.reshape(1, -1)

    if preds.shape[1] <= 4:
        return []

    boxes_xywh = preds[:, :4]
    class_scores = preds[:, 4:]

    class_ids = class_scores.argmax(axis=1)
    confidences = class_scores.max(axis=1)

    detections = []
    for i in range(preds.shape[0]):
        conf = float(confidences[i])
        if conf < conf_threshold:
            continue

        class_id = int(class_ids[i])
        bbox = xywh_to_xyxy(boxes_xywh[i].tolist())
        detections.append(
            Detection(class_id, get_class_name(class_id), conf, bbox)
        )

    return nms(detections, iou_threshold)

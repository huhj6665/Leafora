# -*- coding: utf-8 -*-
"""
异常图片缓存模块
================

旧接口兼容层：检测到病害时保存原始帧。正式运行时由 ``edge.runtime`` 配合
SQLite 队列使用；本类不作为本地归档，也不负责上传完成后的删除。

保存规则：

* ``detections`` 为空 -> 不保存
* ``detections`` 存在 -> 保存未绘制检测框的原始图片
* 缓存数量达到 ``max_images`` -> 停止保存（不删除旧图，不循环覆盖）

用法::

    from data.image_cache import ImageCache

    cache = ImageCache(save_dir="data/cache", max_images=50)
    cache.save(frame, detections)
"""

import os
import time

import cv2

class ImageCache:
    """异常图片本地缓存管理类。"""

    def __init__(self, save_dir="data/cache", max_images=50):
        """
        初始化缓存管理器。

        :param save_dir:    图片保存目录，默认 ``data/cache``
        :param max_images:  最多缓存图片数量，达到后停止保存
        :raises ValueError: max_images 非法（<= 0）时抛出
        """
        if max_images <= 0:
            raise ValueError("max_images 必须大于 0，当前值: {}".format(max_images))

        self.save_dir = save_dir
        self.max_images = int(max_images)

        # 确保保存目录存在
        try:
            os.makedirs(self.save_dir, exist_ok=True)
        except OSError as e:
            print("[WARN] 缓存目录创建失败: {}".format(e))

        # 已缓存图片数量（统计目录中已有图片，避免重复运行导致超量）
        self._count = self._count_existing()

        # 用于生成不重复文件名的序列号（同秒内递增）
        self._last_timestamp = None
        self._seq = 0

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    def _count_existing(self):
        """统计保存目录中已有的图片数量。"""
        if not os.path.isdir(self.save_dir):
            return 0
        try:
            files = os.listdir(self.save_dir)
        except OSError:
            return 0
        return sum(1 for f in files if f.lower().endswith((".jpg", ".jpeg", ".png")))

    def _next_filename(self):
        """生成不重复的文件名，格式：YYYYMMDD_HHMMSS_SSS.jpg。"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if timestamp == self._last_timestamp:
            self._seq += 1
        else:
            self._last_timestamp = timestamp
            self._seq = 1
        return "{}_{:03d}.jpg".format(timestamp, self._seq)

    @staticmethod
    def _draw_detections(image, detections):
        """兼容旧调用名；按冻结规则返回未标注的原始图像副本。"""
        return image.copy()

    # ------------------------------------------------------------------
    # 保存接口
    # ------------------------------------------------------------------
    def save(self, image, detections):
        """
        保存病害对应的原始图片。

        :param image:      OpenCV BGR 图像 (numpy.ndarray)
        :param detections: 检测结果列表 list[Detection]
        :return: 保存成功返回文件路径，未保存返回 None
        """
        # 1. 无检测结果 -> 不保存
        if not detections:
            return None

        # 2. 数量已达上限 -> 停止保存（不删除旧图，不循环覆盖）
        if self._count >= self.max_images:
            print("[WARN] 缓存数量已达上限 {}，停止保存".format(self.max_images))
            return None

        # 3. 输入校验
        if image is None:
            print("[WARN] 输入图像为空，无法保存")
            return None

        # 4. 保存原始帧副本，不把 UI 检测框写入待上传图片
        annotated = self._draw_detections(image, detections)

        # 5. 生成文件名并保存
        filepath = os.path.join(self.save_dir, self._next_filename())
        try:
            success = cv2.imwrite(filepath, annotated)
        except Exception as e:
            print("[ERROR] 图片保存异常: {} -> {}".format(filepath, e))
            return None

        if not success:
            print("[ERROR] 图片写入失败: {}".format(filepath))
            return None

        # 6. 更新计数
        self._count += 1
        print("[INFO] 已缓存异常图片: {} ({}/{})".format(
            filepath, self._count, self.max_images))
        return filepath

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    @property
    def count(self):
        """当前已缓存图片数量。"""
        return self._count

    @property
    def is_full(self):
        """缓存是否已满（达到 max_images）。"""
        return self._count >= self.max_images

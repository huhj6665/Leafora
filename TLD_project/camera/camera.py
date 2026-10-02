# -*- coding: utf-8 -*-
"""
摄像头采集模块
================

负责打开 /dev/video0 摄像头，提供帧读取接口。

用法::

    from camera.camera import Camera

    cam = Camera()          # 默认 /dev/video0
    cam.open()
    frame = cam.read()      # 读取一帧 BGR 图像
    cam.release()
"""

import cv2


class Camera:
    """USB / V4L2 摄像头封装类。"""

    def __init__(self, device="/dev/video0", width=640, height=640, fps=30):
        """
        初始化摄像头参数。

        :param device: 摄像头设备路径，默认 /dev/video0
        :param width:  期望的图像宽度
        :param height: 期望的图像高度
        :param fps:    期望的帧率
        """
        self.device = device
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)

        self._cap = None      # cv2.VideoCapture 对象
        self._opened = False

    # ------------------------------------------------------------------
    # 生命周期接口
    # ------------------------------------------------------------------
    def open(self):
        """
        打开摄像头。

        :return: 成功返回 True
        :raises RuntimeError: 摄像头打开失败时抛出，并给出明确提示
        """
        # 已打开则直接返回，避免重复打开
        if self._opened:
            return True

        # 使用 V4L2 后端读取 /dev/video0（Jetson 平台标准做法）
        self._cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)

        if not self._cap.isOpened():
            self._cap.release()
            self._cap = None
            raise RuntimeError(
                "无法打开摄像头: {}，请检查：\n"
                "  1) 设备是否已连接；\n"
                "  2) 权限是否足够（可尝试: sudo chmod 666 {}）".format(
                    self.device, self.device
                )
            )

        # 设置分辨率与帧率（部分摄像头可能不支持，设置失败不影响读取）
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)

        # 读取实际生效的参数
        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self._cap.get(cv2.CAP_PROP_FPS)

        self._opened = True
        return True

    def read(self):
        """
        读取一帧图像。

        :return: 读取成功返回 BGR 图像(numpy.ndarray)，失败返回 None
        :raises RuntimeError: 摄像头未打开时抛出
        """
        if not self._opened:
            raise RuntimeError("摄像头未打开，请先调用 open()")

        ret, frame = self._cap.read()
        if not ret or frame is None:
            return None
        return frame

    def release(self):
        """释放摄像头资源。"""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._opened = False

    # ------------------------------------------------------------------
    # 辅助接口
    # ------------------------------------------------------------------
    @property
    def is_opened(self):
        """摄像头是否已打开。"""
        return self._opened

    def __enter__(self):
        """支持 with 语法：with Camera() as cam: ..."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出 with 块时自动释放资源。"""
        self.release()
        return False

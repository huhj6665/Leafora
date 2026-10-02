# -*- coding: utf-8 -*-
"""
帧调度器模块
============

控制检测频率：按时间间隔决定是否允许一次模型推理。

设计目标：基于「时间」判断（而非帧数量），以便未来接入无人机飞行速度、
GPS 等外部信息后，可以动态调整抽帧节奏。

用法::

    from utils.frame_scheduler import FrameScheduler

    scheduler = FrameScheduler(interval=0.5)   # 每 500ms 允许一次推理
    if scheduler.should_process():
        detections = engine.infer(frame)
"""

import time


class FrameScheduler:
    """基于时间间隔的抽帧 / 检测调度器。"""

    def __init__(self, interval=0.5):
        """
        初始化调度器。

        :param interval: 检测间隔（秒）。例如 0.5 表示每 500ms 允许一次推理。
        :raises ValueError: interval 非法（<= 0）时抛出
        """
        if interval <= 0:
            raise ValueError("interval 必须大于 0，当前值: {}".format(interval))

        self.interval = float(interval)
        self._last_process_time = None  # 上一次执行推理的时间戳

    def should_process(self):
        """
        判断当前是否应该执行一次推理。

        基于时间判断：距离上一次推理超过 ``interval`` 秒才返回 True，
        并更新内部时间戳；否则返回 False。

        :return: True 表示允许本次推理，False 表示跳过
        """
        now = time.time()

        # 首次调用、或距离上次推理已超过间隔 -> 允许推理
        if self._last_process_time is None or (now - self._last_process_time) >= self.interval:
            self._last_process_time = now
            return True

        return False

    def set_interval(self, interval):
        """
        动态调整检测间隔（用于未来接入无人机速度等做动态抽帧）。

        :param interval: 新的检测间隔（秒）
        :raises ValueError: interval 非法（<= 0）时抛出
        """
        if interval <= 0:
            raise ValueError("interval 必须大于 0，当前值: {}".format(interval))
        self.interval = float(interval)

    def reset(self):
        """重置调度器，使下一次调用 ``should_process`` 立即返回 True。"""
        self._last_process_time = None

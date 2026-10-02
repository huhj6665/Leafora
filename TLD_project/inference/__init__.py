# -*- coding: utf-8 -*-
"""inference 包：AI 推理框架。"""

from .inference_engine import InferenceEngine
from . import yolov11_postprocess as postprocess

__all__ = ["InferenceEngine", "postprocess"]

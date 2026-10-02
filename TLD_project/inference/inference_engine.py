# -*- coding: utf-8 -*-
"""
TensorRT 推理引擎
================

加载 ``models/train_best.engine``，实现真实 TensorRT 推理链路::

    BGR -> RGB -> resize 640x640 -> normalize -> CHW -> TensorRT -> 后处理 -> Detection 列表

同时兼容两种 TensorRT API，运行时自动探测并适配：

* TensorRT 8.5+  新 tensor API（``num_io_tensors`` / ``set_tensor_address`` / ``execute_async_v3``）
* TensorRT 8.2   旧 binding API（``num_bindings`` / ``execute_async_v2``）

用法::

    from inference.inference_engine import InferenceEngine

    engine = InferenceEngine(model_path="models/train_best.engine")
    engine.load()
    detections = engine.infer(frame)      # frame 为 OpenCV BGR 图像
    engine.release()
"""

import os
import threading

import cv2
import numpy as np

try:
    import tensorrt as trt
except ImportError:  # 便于在没有 TRT 的环境中仍可导入本模块
    trt = None

try:
    import pycuda.driver as cuda
except ImportError:
    cuda = None

from inference.yolov11_postprocess import decode_output, scale_detections


class InferenceEngine:
    """TensorRT 推理引擎封装类。"""

    # YOLO11 模型输入尺寸
    INPUT_WIDTH = 640
    INPUT_HEIGHT = 640

    def __init__(self, model_path=None, conf_threshold=0.25, iou_threshold=0.45):
        """
        初始化推理引擎。

        :param model_path:     engine 文件路径（如 models/train_best.engine）
        :param conf_threshold: 置信度阈值
        :param iou_threshold:  NMS 的 IoU 阈值
        """
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold

        # TensorRT 运行时对象
        self._logger = None
        self._runtime = None
        self._engine = None        # tensorrt.ICudaEngine
        self._context = None       # tensorrt.IExecutionContext

        # 输入 / 输出 buffer
        self._input_name = None
        self._output_name = None
        self._input_index = None
        self._output_index = None
        self._input_shape = None
        self._output_shape = None
        self._input_dtype = None
        self._input_host = None    # numpy 输入 buffer（主机内存）
        self._output_host = None   # numpy 输出 buffer（主机内存）
        self._input_device = None  # 输入显存 buffer
        self._output_device = None # 输出显存 buffer
        self._stream = None        # CUDA stream

        # True: TRT 8.5+ 新 tensor API；False: TRT 8.2 旧 binding API
        self._use_new_api = False
        self._loaded = False
        self._cuda_context = None
        self._owner_thread = None

    # ------------------------------------------------------------------
    # 加载接口
    # ------------------------------------------------------------------
    def load(self, model_path=None):
        if self._loaded:
            self._check_owner()
            return True
        if cuda is None:
            raise RuntimeError("未安装 pycuda，请使用 JetPack 系统环境")
        if trt is None:
            raise RuntimeError("未安装 TensorRT Python binding，请使用 JetPack 系统环境")
        self._owner_thread = threading.get_ident()
        try:
            cuda.init()
            self._cuda_context = cuda.Device(0).make_context()
            return self._load_engine(model_path)
        except Exception:
            self.release()
            raise

    def _check_owner(self):
        if self._owner_thread is not None and self._owner_thread != threading.get_ident():
            raise RuntimeError("CUDA 加载、推理与释放必须由同一个 YOLO 工作线程执行")

    def _load_engine(self, model_path=None):
        """
        加载 TensorRT engine。

        流程：读取 engine 文件 -> 反序列化 -> 创建 ExecutionContext -> 分配 buffer。

        :param model_path: 覆盖默认的 engine 文件路径
        :return: 加载成功返回 True
        """
        if trt is None:
            raise RuntimeError("未安装 tensorrt，请先安装 TensorRT Python 包")
        if cuda is None:
            raise RuntimeError("未安装 pycuda，请先安装 pycuda")

        if model_path is not None:
            self.model_path = model_path

        if not self.model_path or not os.path.isfile(self.model_path):
            raise FileNotFoundError("engine 文件不存在: {}".format(self.model_path))

        # 1. 创建 Runtime 并反序列化 engine
        self._logger = trt.Logger(trt.Logger.WARNING)
        self._runtime = trt.Runtime(self._logger)

        with open(self.model_path, "rb") as f:
            engine_data = f.read()

        self._engine = self._runtime.deserialize_cuda_engine(engine_data)
        if self._engine is None:
            raise RuntimeError("反序列化 engine 失败: {}".format(self.model_path))

        # 2. 创建 ExecutionContext
        self._context = self._engine.create_execution_context()
        if self._context is None:
            raise RuntimeError("创建 ExecutionContext 失败")

        # 3. 探测 TensorRT API 版本
        self._use_new_api = hasattr(self._engine, "num_io_tensors")

        # 4. 分配输入 / 输出 buffer
        self._allocate_buffers()

        # 5. 创建 CUDA stream
        self._stream = cuda.Stream()

        self._loaded = True
        return True

    # ------------------------------------------------------------------
    # buffer 分配（兼容两种 API）
    # ------------------------------------------------------------------
    def _allocate_buffers(self):
        """根据探测到的 API 版本分派到对应实现。"""
        if self._use_new_api:
            self._allocate_buffers_new_api()
        else:
            self._allocate_buffers_old_api()

    def _allocate_buffers_new_api(self):
        """TensorRT 8.5+：基于 tensor 名称的分配方式。"""
        engine = self._engine
        context = self._context

        for i in range(engine.num_io_tensors):
            name = engine.get_tensor_name(i)
            dtype = trt.nptype(engine.get_tensor_dtype(name))
            mode = engine.get_tensor_mode(name)

            if mode == trt.TensorIOMode.INPUT:
                shape = tuple(engine.get_tensor_shape(name))
                # 动态 shape（-1）时固定为 1x3x640x640
                if -1 in shape:
                    shape = (1, 3, self.INPUT_HEIGHT, self.INPUT_WIDTH)
                    context.set_input_shape(name, shape)
                host = np.empty(shape, dtype=dtype)
                device = cuda.mem_alloc(host.nbytes)
                self._input_name = name
                self._input_index = i
                self._input_shape = shape
                self._input_dtype = dtype
                self._input_host = host
                self._input_device = device
            else:
                shape = tuple(context.get_tensor_shape(name))
                host = np.empty(shape, dtype=dtype)
                device = cuda.mem_alloc(host.nbytes)
                self._output_name = name
                self._output_index = i
                self._output_shape = shape
                self._output_host = host
                self._output_device = device

    def _allocate_buffers_old_api(self):
        """TensorRT 8.2：基于 binding 索引的分配方式。"""
        engine = self._engine
        context = self._context

        for i in range(engine.num_bindings):
            name = engine.get_binding_name(i)
            dtype = trt.nptype(engine.get_binding_dtype(i))
            is_input = engine.binding_is_input(i)

            if is_input:
                shape = tuple(engine.get_binding_shape(i))
                # 动态 shape（-1）时固定为 1x3x640x640
                if -1 in shape:
                    shape = (1, 3, self.INPUT_HEIGHT, self.INPUT_WIDTH)
                    context.set_binding_shape(i, shape)
            else:
                shape = tuple(context.get_binding_shape(i))

            host = np.empty(shape, dtype=dtype)
            device = cuda.mem_alloc(host.nbytes)

            if is_input:
                self._input_name = name
                self._input_index = i
                self._input_shape = shape
                self._input_dtype = dtype
                self._input_host = host
                self._input_device = device
            else:
                self._output_name = name
                self._output_index = i
                self._output_shape = shape
                self._output_host = host
                self._output_device = device

    # ------------------------------------------------------------------
    # 预处理 / 执行推理
    # ------------------------------------------------------------------
    def _preprocess(self, frame):
        """
        BGR -> RGB -> resize 640x640 -> normalize -> CHW -> (1, 3, 640, 640)。

        :param frame: OpenCV BGR 图像 (numpy.ndarray)
        :return: 预处理后的输入张量 (numpy.ndarray)
        """
        # 1. BGR -> RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # 2. resize 到 640x640
        resized = cv2.resize(rgb, (self.INPUT_WIDTH, self.INPUT_HEIGHT))
        # 3. normalize 到 [0, 1]（YOLO11 仅做 /255，无均值方差）
        x = resized.astype(np.float32) / 255.0
        # 4. HWC -> CHW
        x = np.transpose(x, (2, 0, 1))
        # 5. 添加 batch 维度 -> (1, 3, 640, 640)
        x = np.expand_dims(x, axis=0)
        x = np.ascontiguousarray(x, dtype=self._input_dtype)
        return x

    def _execute(self):
        """执行一次异步推理并等待完成。"""
        if self._use_new_api:
            self._context.set_tensor_address(self._input_name, int(self._input_device))
            self._context.set_tensor_address(self._output_name, int(self._output_device))
            self._context.execute_async_v3(stream_handle=self._stream.handle)
        else:
            bindings = [0] * self._engine.num_bindings
            bindings[self._input_index] = int(self._input_device)
            bindings[self._output_index] = int(self._output_device)
            self._context.execute_async_v2(bindings=bindings, stream_handle=self._stream.handle)

        self._stream.synchronize()

    # ------------------------------------------------------------------
    # 推理接口
    # ------------------------------------------------------------------
    def infer(self, image):
        """
        对输入图像执行完整推理，返回检测结果列表。

        :param image: OpenCV BGR 图像 (numpy.ndarray)
        :return: detections: list[Detection]，bbox 为原始图像像素坐标 [x1, y1, x2, y2]
        :raises RuntimeError: engine 未加载时抛出
        """
        self._check_owner()
        if not self._loaded:
            raise RuntimeError("推理引擎未加载，请先调用 load()")

        orig_h, orig_w = image.shape[:2]

        # 1. 预处理
        x = self._preprocess(image)

        # 2. 输入拷贝到显存
        self._input_host[...] = x
        cuda.memcpy_htod(self._input_device, self._input_host)

        # 3. 执行推理
        self._execute()

        # 4. 输出拷贝回主机
        cuda.memcpy_dtoh(self._output_host, self._output_device)

        # 5. 后处理（解析 -> 置信度 -> class_id -> bbox -> NMS）
        detections = decode_output(self._output_host, self.conf_threshold, self.iou_threshold)

        # 6. 归一化坐标 -> 原始图像像素坐标
        detections = scale_detections(detections, orig_w, orig_h)

        return detections

    # ------------------------------------------------------------------
    # 状态查询 / 资源释放
    # ------------------------------------------------------------------
    @property
    def is_loaded(self):
        """engine 是否已加载。"""
        return self._loaded

    def release(self):
        """所有 CUDA 资源仍在所属上下文当前时释放，最后 pop/detach。"""
        self._check_owner()
        context = self._cuda_context
        try:
            if self._stream is not None:
                self._stream.synchronize()
        finally:
            try:
                for allocation in (self._input_device, self._output_device):
                    if allocation is not None:
                        try:
                            allocation.free()
                        except Exception:
                            # 出错时仍继续释放其它资源并 pop/detach，不能遗留 context stack。
                            pass
            finally:
                self._input_device = None
                self._output_device = None
                self._input_host = None
                self._output_host = None
                self._stream = None
                self._context = None
                self._engine = None
                self._runtime = None
                self._logger = None
                self._loaded = False
                self._cuda_context = None
                self._owner_thread = None
                if context is not None:
                    try:
                        context.pop()
                    finally:
                        context.detach()

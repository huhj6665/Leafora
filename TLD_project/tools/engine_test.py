#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TensorRT Engine 基础测试

功能:
1. 加载 .engine 文件
2. 查看输入输出 binding
3. 构造随机输入
4. 执行一次推理
5. 打印输出数据

用于确认 YOLO11 TensorRT 输出格式
"""

import tensorrt as trt
import numpy as np
import pycuda.driver as cuda
import pycuda.autoinit


# ==========================
# 参数配置
# ==========================

ENGINE_PATH = "../models/train_best.engine"

LOGGER = trt.Logger(trt.Logger.INFO)


# ==========================
# 加载engine
# ==========================

def load_engine(engine_path):

    print("\n[INFO] Loading engine...")

    with open(engine_path, "rb") as f:
        engine_data = f.read()

    runtime = trt.Runtime(LOGGER)

    engine = runtime.deserialize_cuda_engine(engine_data)

    if engine is None:
        raise RuntimeError("Engine loading failed!")

    print("[INFO] Engine loaded successfully")

    return engine


# ==========================
# 查看binding
# ==========================

def inspect_engine(engine):

    print("\n========== Engine Binding Info ==========")

    for i in range(engine.num_io_tensors):

        name = engine.get_tensor_name(i)

        shape = engine.get_tensor_shape(name)

        dtype = engine.get_tensor_dtype(name)

        mode = engine.get_tensor_mode(name)

        print(f"\nTensor {i}")

        print("Name :", name)
        print("Shape:", shape)
        print("Type :", dtype)
        print("Mode :", mode)

    print("\n========================================")


# ==========================
# 执行一次推理
# ==========================

def inference_test(engine):

    context = engine.create_execution_context()


    inputs = {}
    outputs = {}

    bindings = []


    print("\n========== Allocate Memory ==========")


    for i in range(engine.num_io_tensors):

        name = engine.get_tensor_name(i)

        shape = engine.get_tensor_shape(name)

        dtype = trt.nptype(
            engine.get_tensor_dtype(name)
        )


        size = int(
            np.prod(shape)
        )


        host_mem = np.empty(
            size,
            dtype=dtype
        )


        device_mem = cuda.mem_alloc(
            host_mem.nbytes
        )


        bindings.append(int(device_mem))


        if engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:

            inputs[name] = (
                host_mem,
                device_mem
            )

        else:

            outputs[name] = (
                host_mem,
                device_mem
            )


        print(
            name,
            shape,
            dtype
        )


    print("\n========== Generate Random Input ==========")


    # 输入随机数据
    for name, (host, device) in inputs.items():

        print("Input:", name)

        host[:] = np.random.random(
            host.shape
        )


        cuda.memcpy_htod(
            device,
            host
        )


        context.set_tensor_address(
            name,
            int(device)
        )


    # 设置输出地址

    for name, (host, device) in outputs.items():

        context.set_tensor_address(
            name,
            int(device)
        )


    print("\n========== Execute ==========")


    context.execute_async_v3(
        stream_handle=0
    )


    print("[INFO] Inference finished")


    print("\n========== Output Preview ==========")


    for name, (host, device) in outputs.items():

        cuda.memcpy_dtoh(
            host,
            device
        )

        print("\nOutput name:", name)

        print(
            "Shape:",
            host.shape
        )

        print(
            "First values:"
        )

        print(
            host[:20]
        )


# ==========================
# main
# ==========================

if __name__ == "__main__":

    print(
        "TensorRT version:",
        trt.__version__
    )


    engine = load_engine(
        ENGINE_PATH
    )


    inspect_engine(
        engine
    )


    inference_test(
        engine
    )


    print("\n========== Test Finished ==========")

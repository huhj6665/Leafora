import tensorrt as trt
import os


ONNX_PATH = "../models/train_best.onnx"
ENGINE_PATH = "../models/train_best.engine"


TRT_LOGGER = trt.Logger(trt.Logger.INFO)


def build_engine():

    print("TensorRT version:", trt.__version__)

    builder = trt.Builder(TRT_LOGGER)

    network_flags = (
        1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    )

    network = builder.create_network(network_flags)

    parser = trt.OnnxParser(
        network,
        TRT_LOGGER
    )


    print("Loading ONNX model...")


    with open(ONNX_PATH, "rb") as model:
        if not parser.parse(model.read()):

            print("ONNX parsing failed!")

            for i in range(parser.num_errors):
                print(parser.get_error(i))

            return None


    print("ONNX parsed successfully")


    config = builder.create_builder_config()


    # 设置显存工作空间
    config.max_workspace_size = 1 << 30


    # 开启FP16
    if builder.platform_has_fast_fp16:

        print("FP16 enabled")

        config.set_flag(
            trt.BuilderFlag.FP16
        )


    print("Building engine...")


    engine = builder.build_serialized_network(
        network,
        config
    )


    if engine is None:

        print("Engine build failed!")

        return None


    with open(ENGINE_PATH, "wb") as f:

        f.write(engine)


    print("Engine saved:")
    print(ENGINE_PATH)



if __name__ == "__main__":

    build_engine()

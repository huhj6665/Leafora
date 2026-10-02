#!/bin/bash

MODEL_DIR="../models"

ONNX_MODEL=${MODEL_DIR}/train_best.onnx
ENGINE_MODEL=${MODEL_DIR}/train_best.engine


echo "=============================="
echo "TensorRT Engine Build Start"
echo "=============================="


/usr/src/tensorrt/bin/trtexec \
--onnx=${ONNX_MODEL} \
--saveEngine=${ENGINE_MODEL} \
--fp16


if [ $? -eq 0 ]
then
    echo "=============================="
    echo "Build Success!"
    echo ${ENGINE_MODEL}
    echo "=============================="
else
    echo "Build Failed!"
fi

# 素材与模型

`demo-field-a01.jpg` 是 A-01 演示烟田底图。前端在 `Web/frontend/src/assets/` 保留页面实际引用的首页、烟田和小程序说明素材，未使用的设计试稿不进入发布源码。

地图的 WGS84 校准参数为确定性的模拟值，不能用于真实测绘、导航或飞行控制。

首次导入 A-01 前，将底图复制到后端存储目录：

```powershell
# 在项目根目录运行
New-Item -ItemType Directory -Force Web/backend/storage/fields
Copy-Item assets/demo-field-a01.jpg Web/backend/storage/fields/demo-field-a01.jpg
```

数据库、用户图片和运行数据不随源码分发。模型文件也不分发：

- Jetson：自行准备兼容目标 JetPack / TensorRT 的 `TLD_project/models/train_best.engine`。
- ONNX 转换输入：自行准备 `TLD_project/models/train_best.onnx`。
- 云端：自行准备 `Web/model_service/weights/train_best.pt`，或通过本地环境配置权重路径。

图片和模型的来源及公开分发授权尚未在项目中完整登记；项目所有者应在公开仓库前确认。第三方组件按各自许可证使用，本说明不替代其授权条款。

# RT-DETR-L 云端推理服务

独立于 Web 后端的二次识别服务。Jetson 原始 `detection` 与云端 `cloud_detection` 分离保存。

- 模型：RT-DETR-L（Ultralytics RTDETR 接口）
- 任务：object detection
- 类别：`Frogeye` / `Mosaic` / `Budworm damage` / `Wildfire`
- 默认输入尺寸：800

## 目录

```
model_service/
├── app/                 # main / config / inference / service / schemas / cli
├── weights/             # 请手动放入 train_best.pt
├── test_images/incoming/ # 手动放入待测 JPG/PNG
├── outputs/annotated/    # 批量推理标注图输出
├── requirements.txt
└── .env.example
```

## 安装（用户部署权重后执行）

```powershell
cd model_service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt          # 会安装 torch / ultralytics
cp .env.example .env
# 将权重放到 weights/train_best.pt
```

## 启动

```powershell
cd model_service
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002
```

> 端口以实际占用为准（本机此前计划使用 8002）；请在 `backend/.env` 的 `MODEL_SERVICE_URL` 中保持一致，不要硬编码。

- 健康检查：`http://127.0.0.1:8002/health`
- 推理：`POST http://127.0.0.1:8002/predict`（multipart `image`）

## 响应结构

`/predict` 成功返回：

```json
{
  "model_name": "RT-DETR-L",
  "model_version": "v1.0",
  "weights_identifier": "sha256 前 16 位",
  "has_target": true,
  "results": [
    {"class": "Frogeye", "confidence": 0.9593, "bbox": [102, 63, 560, 635]}
  ],
  "annotated_image_base64": "..."
}
```

结果中的类别字段统一为 `class`，与后端存储、前端展示保持一致。

## 模型未部署

权重缺失时服务仍可启动，`/health` 返回 `model_unavailable`，`/predict` 返回 503。
Web 后端此时仍允许图片上传，推理任务置 `model_unavailable`。

## 批量图片独立测试（不需要 PostgreSQL）

```powershell
cd model_service
.venv\Scripts\python.exe -m app.cli --input test_images/incoming --output outputs/annotated
```

读取 `test_images/incoming` 内的 JPG/PNG，逐张推理并输出标注图 + JSON。

## bbox 坐标说明

返回的 `bbox` 已转换回**原始上传图片像素坐标** `[x1, y1, x2, y2]`，
不会把 resize 到 800×800 的网络输入坐标当作原图坐标。

## 模型版本

权重标识使用权重文件 **SHA-256 前 16 位** + `MODEL_VERSION`，
不单独以 `RT-DETR-L` 作为永久版本号（未来重训练仍叫 RT-DETR-L）。

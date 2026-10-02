"""Virtual Jetson HTTP 客户端：账号绑定与图片上传。"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from scripts.mock_jetson.config import MockConfig, mask_secret

CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


class DeviceBinder:
    """Deprecated compatibility shell; formal pairing is QR/session based."""
    def __init__(self, config: MockConfig) -> None:
        self.config = config
        self.base = config.backend_base_url.rstrip("/")

    def bind(self) -> dict:
        raise RuntimeError("已移除用户名自动绑定；请使用设备动态配对会话和已登录手机号小程序扫码确认。")


class ImageUploader:
    def __init__(self, config: MockConfig) -> None:
        self.config = config
        self.base = config.backend_base_url.rstrip("/")
        if self.config.http_debug:
            print(
                "[HTTP config] "
                f"device_id={self.config.device_id} "
                f"secret={mask_secret(self.config.device_secret)} "
                f"endpoint={self.base}/inspection/device-upload"
            )

    def _debug_result(self, status_code: int, body: dict, attempts: int) -> None:
        if not self.config.http_debug:
            return
        rendered = json.dumps(body, ensure_ascii=False, default=str)
        print(f"[HTTP upload] status={status_code} attempts={attempts} body={rendered[:500]}")

    def upload(
        self,
        data_id: str,
        image_id: str,
        image_path: str | Path,
        inspection_id: str | None = None,
        timestamp: str | None = None,
    ) -> dict:
        if not self.config.device_secret:
            body = {
                "error": "MOCK_DEVICE_SECRET 为空；请检查 scripts/mock_jetson/.env 是否存在且已配置",
            }
            self._debug_result(0, body, 0)
            return {"http_status": 0, "body": body, "attempts": 0}

        path = Path(image_path)
        content = path.read_bytes()
        form = {"data_id": data_id, "image_id": image_id}
        if inspection_id:
            form["inspection_id"] = inspection_id
        if timestamp:
            form["timestamp"] = timestamp
        headers = {"X-Device-ID": self.config.device_id, "X-Device-Secret": self.config.device_secret}
        last_status, last_body = 0, {}
        for attempt in range(self.config.upload_retries + 1):
            try:
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(
                        f"{self.base}/inspection/device-upload",
                        data=form,
                        files={"image": (path.name, content, CONTENT_TYPES.get(path.suffix.lower(), "image/jpeg"))},
                        headers=headers,
                    )
                last_status = response.status_code
                try:
                    last_body = response.json()
                except ValueError:
                    last_body = {"error": response.text[:200]}
                if last_status == 404 and attempt < self.config.upload_retries:
                    self._debug_result(last_status, last_body, attempt + 1)
                    time.sleep(self.config.upload_retry_interval)
                    continue
                self._debug_result(last_status, last_body, attempt + 1)
                return {"http_status": last_status, "body": last_body, "attempts": attempt + 1}
            except httpx.HTTPError as exc:
                last_body = {"error": str(exc)}
                self._debug_result(last_status, last_body, attempt + 1)
                if attempt < self.config.upload_retries:
                    time.sleep(self.config.upload_retry_interval)
                    continue
        return {"http_status": last_status, "body": last_body, "attempts": self.config.upload_retries + 1}

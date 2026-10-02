# -*- coding: utf-8 -*-
"""设备认证 HTTP、动态配对和幂等图片上传。"""

import json
import mimetypes
import os
import re
import socket
import uuid
from urllib import error, parse, request

from .protocol import PAIRING_QR_VERSION


class HttpClientError(RuntimeError):
    pass


def _unwrap(body):
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    return body


class DeviceHttpClient(object):
    def __init__(self, base_url, device_id, device_secret, timeout_s=15.0):
        self.base_url = (base_url or "").rstrip("/")
        self.device_id = device_id
        self._device_secret = device_secret
        self.timeout_s = float(timeout_s)

    def _headers(self, content_type=None):
        headers = {
            "X-Device-ID": self.device_id,
            "X-Device-Secret": self._device_secret,
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _call(self, method, path, body=None, content_type=None):
        if not self.base_url or not self._device_secret:
            raise HttpClientError("HTTP 设备配置不完整")
        target = self.base_url + path
        req = request.Request(target, data=body, headers=self._headers(content_type))
        req.get_method = lambda: method
        try:
            response = request.urlopen(req, timeout=self.timeout_s)
            try:
                raw = response.read()
                status = response.getcode()
            finally:
                response.close()
        except error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        except (error.URLError, socket.timeout, OSError) as exc:
            raise HttpClientError("HTTP 请求失败: {}".format(type(exc).__name__))
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError):
            raise HttpClientError("HTTP {} 返回无法确认的响应".format(status))
        if status < 200 or status >= 300:
            # 不将未经脱敏的服务端 detail/认证 Header 带到终端。
            raise HttpClientError("HTTP {}{}".format(status, "：设备认证失败" if status in (401, 403) else "：请求未成功"))
        return parsed

    def request_json(self, method, path, payload=None):
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._call(method, path, body, "application/json")

    def create_pairing_session(self):
        body = self.request_json("POST", "/api/device/pairing-sessions", {})
        data = _unwrap(body)
        required = ("pairing_session_id", "pairing_token", "expires_at")
        if not isinstance(data, dict) or any(not data.get(key) for key in required):
            raise HttpClientError("配对会话响应字段不完整")
        return data

    def get_pairing_session(self, pairing_session_id):
        safe_id = parse.quote(str(pairing_session_id), safe="")
        return _unwrap(self.request_json(
            "GET", "/api/device/pairing-sessions/{}".format(safe_id)
        ))

    @staticmethod
    def pairing_payload(device_id, session):
        return {
            "type": "tld_device_pairing",
            "version": PAIRING_QR_VERSION,
            "device_id": device_id,
            "pairing_session_id": session["pairing_session_id"],
            "pairing_token": session["pairing_token"],
            "expires_at": session["expires_at"],
        }

    def generate_pairing_qr(self, session, output_dir):
        try:
            import qrcode
        except ImportError:
            raise HttpClientError("缺少 qrcode 依赖，无法生成配对二维码")
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", session["pairing_session_id"])
        path = os.path.join(output_dir, "pairing_{}.png".format(safe_id))
        rendered = json.dumps(
            self.pairing_payload(self.device_id, session),
            ensure_ascii=False, separators=(",", ":")
        )
        image = qrcode.make(rendered)
        image.save(path)
        return path

    @staticmethod
    def _multipart(fields, image_path):
        boundary = "----TLD{}".format(uuid.uuid4().hex)
        chunks = []
        for name, value in fields.items():
            chunks.append(("--{}\r\n".format(boundary)).encode("ascii"))
            chunks.append(('Content-Disposition: form-data; name="{}"\r\n\r\n'.format(name)).encode("ascii"))
            chunks.append(str(value).encode("utf-8"))
            chunks.append(b"\r\n")
        filename = os.path.basename(image_path)
        content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
        chunks.append(("--{}\r\n".format(boundary)).encode("ascii"))
        chunks.append(('Content-Disposition: form-data; name="image"; filename="{}"\r\n'.format(filename)).encode("utf-8"))
        chunks.append(("Content-Type: {}\r\n\r\n".format(content_type)).encode("ascii"))
        with open(image_path, "rb") as handle:
            chunks.append(handle.read())
        chunks.append(b"\r\n")
        chunks.append(("--{}--\r\n".format(boundary)).encode("ascii"))
        return b"".join(chunks), "multipart/form-data; boundary={}".format(boundary)

    def upload_image(self, image_id, inspection_id, data_id, captured_at, image_path):
        if not os.path.isfile(image_path):
            raise HttpClientError("待上传临时图片不存在")
        fields = {
            "inspection_id": inspection_id,
            "data_id": data_id,
            "image_id": image_id,
            "timestamp": captured_at,
        }
        body, content_type = self._multipart(fields, image_path)
        response = self._call(
            "POST", "/api/inspection/device-upload", body, content_type
        )
        if response.get("code") != 0:
            raise HttpClientError("云端业务结果未确认成功")
        data = _unwrap(response)
        returned_id = data.get("image_id") if isinstance(data, dict) else None
        if returned_id != image_id:
            raise HttpClientError("云端返回的 image_id 与请求不一致")
        return response

"""模型服务瞬时故障的有界重试测试。"""

from app.services import model_client


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = ""

    def json(self):
        return self._payload


class _Client:
    responses = []
    calls = 0

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        response = self.responses[self.calls]
        self.__class__.calls += 1
        return response


async def _no_sleep(_seconds):
    return None


async def test_transient_502_retries_then_succeeds(monkeypatch):
    _Client.responses = [
        _Response(502),
        _Response(200, {"status": "completed", "results": [], "has_target": False}),
    ]
    _Client.calls = 0
    monkeypatch.setattr(model_client.settings, "MODEL_SERVICE_URL", "http://model")
    monkeypatch.setattr(model_client.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(model_client.asyncio, "sleep", _no_sleep)

    result = await model_client.submit_image(b"image", "image/jpeg", "device", "data")

    assert _Client.calls == 2
    assert result["status"] == "completed"


async def test_repeated_502_is_model_unavailable(monkeypatch):
    _Client.responses = [_Response(502), _Response(502)]
    _Client.calls = 0
    monkeypatch.setattr(model_client.settings, "MODEL_SERVICE_URL", "http://model")
    monkeypatch.setattr(model_client.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(model_client.asyncio, "sleep", _no_sleep)

    result = await model_client.submit_image(b"image", "image/jpeg", "device", "data")

    assert _Client.calls == 2
    assert result == {
        "available": False,
        "status": "model_unavailable",
        "reason": "model_service_http_502",
    }

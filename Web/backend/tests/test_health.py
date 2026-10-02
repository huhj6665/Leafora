"""健康检查接口测试."""


async def test_health(client):
    """健康检查返回数据库与环境状态."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["environment"] == "test"
    assert data["sms_configured"] is False  # 测试环境未配置阿里云凭据

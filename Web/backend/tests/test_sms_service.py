"""短信发送业务与阿里云错误分类测试（不发送真实短信）."""
import pytest

from app.core.exceptions import BusinessError
from app.services.rate_limit import rate_limiter
from app.services.sms import get_sms_provider, reset_sms_provider
from app.services.sms.aliyun import (
    AliyunSMSProvider,
    _is_rate_limit,
    _to_business_error,
)
from app.services import sms_service
from app.services.sms.mock import MockSMSProvider

PHONE = "13800001111"


async def _enable_rate_limit(monkeypatch):
    monkeypatch.setattr(sms_service.settings, "RATE_LIMIT_ENABLED", True)
    rate_limiter.reset()


async def test_failed_send_does_not_consume_quota(monkeypatch):
    """发送失败不消耗限流额度，可立即重试."""
    await _enable_rate_limit(monkeypatch)
    reset_sms_provider()
    provider = get_sms_provider()
    assert isinstance(provider, MockSMSProvider)
    provider.fail_send = True

    with pytest.raises(BusinessError) as exc_info:
        await sms_service.send_verification_code(PHONE, "1.2.3.4")
    assert exc_info.value.status_code == 502

    # 失败后额度未被消耗，仍允许再次发送
    assert rate_limiter.check(f"phone:interval:{PHONE}", 1, 60).allowed


async def test_successful_send_consumes_quota(monkeypatch):
    """发送成功后消耗额度，短时间重复发送被拦截."""
    await _enable_rate_limit(monkeypatch)
    reset_sms_provider()
    provider = get_sms_provider()
    assert isinstance(provider, MockSMSProvider)
    provider.fail_send = False

    await sms_service.send_verification_code(PHONE, "1.2.3.4")

    # 成功后 phone:interval 窗口（1 次/60s）已满
    assert not rate_limiter.check(f"phone:interval:{PHONE}", 1, 60).allowed


async def test_success_after_failure(monkeypatch):
    """失败后立即可成功重试，不被错误限流."""
    await _enable_rate_limit(monkeypatch)
    reset_sms_provider()
    provider = get_sms_provider()
    assert isinstance(provider, MockSMSProvider)

    provider.fail_send = True
    with pytest.raises(BusinessError):
        await sms_service.send_verification_code(PHONE, "1.2.3.4")

    provider.fail_send = False
    result = await sms_service.send_verification_code(PHONE, "1.2.3.4")
    assert result["phone"] == "138****1111"


# ---- 阿里云错误分类（纯函数，无需 SDK）----


def test_is_rate_limit_hints():
    assert _is_rate_limit("isv.BUSINESS_LIMIT_CONTROL")
    assert _is_rate_limit("isv.FLOW_LIMIT")
    assert not _is_rate_limit("isv.SMS_SIGNATURE_ILLEGAL")
    assert not _is_rate_limit("InvalidAccessKeyId.NotFound")
    assert not _is_rate_limit(None)


def test_to_business_error_status_codes():
    assert _to_business_error("ALIYUN_RATE_LIMIT").status_code == 429
    assert _to_business_error("SMS_CONFIG_ERROR").status_code == 500
    assert _to_business_error("ALIYUN_API_ERROR").status_code == 502
    assert _to_business_error("ALIYUN_NETWORK_ERROR").status_code == 502


async def test_aliyun_config_error_without_credentials():
    """缺少 AccessKey：send_code 返回 SMS_CONFIG_ERROR（500），不调用网络."""
    provider = AliyunSMSProvider(
        access_key_id="",
        access_key_secret="",
        sign_name="恒创联众",
        template_code="100001",
    )
    with pytest.raises(BusinessError) as exc_info:
        await provider.send_code(PHONE)
    assert exc_info.value.status_code == 500

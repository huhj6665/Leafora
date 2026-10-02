
# -*- coding: utf-8 -*-
"""
TLD 智能巡检平台
阿里云号码认证服务（短信认证）

功能：
1. 使用 SendSmsVerifyCode 发送短信验证码
2. 使用 CheckSmsVerifyCode 核验验证码
3. 支持阿里云动态生成验证码
4. 短信模板参数合法性检查
5. 短信异常分类与脱敏日志

当前使用：
    系统赠送签名：恒创联众
    登录/注册模板：100001

模板变量：
    code：短信验证码
    min ：验证码有效分钟数

注意：
    阿里云 AccessKey 从项目配置读取。
    不记录验证码、完整手机号和 AccessKey。
"""

import json
import logging
from typing import Optional, Tuple

from app.core.config import settings
from app.core.exceptions import BusinessError
from app.services.sms.base import SMSProvider
from app.utils.phone import mask_phone


# ============================================================
# 一、基础配置
# ============================================================

logger = logging.getLogger("app.sms.aliyun")

# 阿里云号码认证 API 地址
DEFAULT_ENDPOINT = "dypnsapi.aliyuncs.com"

# 中国大陆国家码
COUNTRY_CODE = "86"

# 同一手机号发送间隔（秒）
SEND_INTERVAL = 60

# 默认短信模板参数
DEFAULT_TEMPLATE_PARAM = json.dumps(
    {
        "code": "##code##",
        "min": "5"
    },
    ensure_ascii=False
)

# 阿里云频率限制错误码关键字
_RATE_LIMIT_HINTS = (
    "LIMIT",
    "CONTROL",
    "FLOW",
    "FREQUENCY",
    "THROTTLE",
    "QUOTA",
    "OVER"
)


# ============================================================
# 二、错误分类辅助函数
# ============================================================

def _is_rate_limit(code: Optional[str]) -> bool:
    """判断是否属于阿里云频率限制类错误。"""

    if not code:
        return False

    upper_code = str(code).upper()

    return any(
        hint in upper_code
        for hint in _RATE_LIMIT_HINTS
    )


def _extract_request_id(
    exc: BaseException
) -> Optional[str]:
    """
    从阿里云 SDK 异常中提取 RequestId。
    """

    for attr in (
        "request_id",
        "requestId",
        "RequestId"
    ):

        value = getattr(exc, attr, None)

        if value:
            return str(value)

    data = getattr(exc, "data", None)

    if isinstance(data, dict):

        for key in (
            "RequestId",
            "requestId"
        ):

            value = data.get(key)

            if value:
                return str(value)

    return None


def _to_business_error(
    category: str,
    operation: str = "send"
) -> BusinessError:
    """
    将阿里云异常转换为项目统一业务异常。

    operation:
        send   发送验证码
        verify 核验验证码
    """

    if category == "ALIYUN_RATE_LIMIT":

        return BusinessError(
            "操作过于频繁，请稍后再试",
            code=429,
            status_code=429
        )

    if category == "SMS_CONFIG_ERROR":

        return BusinessError(
            "短信认证服务配置异常，请联系管理员",
            code=500,
            status_code=500
        )

    if operation == "verify":

        return BusinessError(
            "验证码核验服务暂不可用，请稍后再试",
            code=502,
            status_code=502
        )

    return BusinessError(
        "验证码发送失败，请稍后再试",
        code=502,
        status_code=502
    )


# ============================================================
# 三、阿里云短信认证服务
# ============================================================

class AliyunSMSProvider(SMSProvider):
    """
    阿里云号码认证服务提供者。

    与现有 SMSProvider 接口保持兼容。
    """

    name = "aliyun"

    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        sign_name: str,
        template_code: str,
        endpoint: str = DEFAULT_ENDPOINT,
        template_param: str = DEFAULT_TEMPLATE_PARAM,
        code_length: int = 6,
        valid_time: int = 300,
    ) -> None:

        self._access_key_id = access_key_id
        self._access_key_secret = access_key_secret

        self._sign_name = sign_name
        self._template_code = template_code

        self._endpoint = endpoint

        self._template_param = template_param

        self._code_length = code_length
        self._valid_time = valid_time

        self._client = None
        self._models = None

    # ========================================================
    # 四、初始化阿里云 SDK
    # ========================================================

    def _ensure_sdk(self):
        """
        懒加载阿里云 SDK。

        避免在不需要真实短信服务时强制初始化客户端。
        """

        if self._client is not None:

            return self._client, self._models

        try:

            from alibabacloud_dypnsapi20170525.client import (
                Client as DypnsapiClient
            )

            from alibabacloud_dypnsapi20170525 import (
                models as dypnsapi_models
            )

            from alibabacloud_tea_openapi import (
                models as open_api_models
            )

        except ImportError as exc:

            logger.error(
                "SMS_CONFIG_ERROR: "
                "阿里云短信认证 SDK 未安装"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            ) from exc

        try:

            config = open_api_models.Config(
                access_key_id=self._access_key_id,
                access_key_secret=self._access_key_secret,
                endpoint=self._endpoint
            )

            client = DypnsapiClient(config)

        except Exception as exc:

            logger.error(
                "SMS_CONFIG_ERROR: "
                "阿里云客户端初始化失败，"
                "exception_type=%s",
                type(exc).__name__
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            ) from exc

        self._client = client
        self._models = dypnsapi_models

        return self._client, self._models

    # ========================================================
    # 五、短信模板参数检查
    # ========================================================

    def _validate_template_param(self) -> str:
        """
        检查模板参数与当前登录/注册模板是否匹配。

        当前模板 100001 包含：
            ${code}
            ${min}

        code 必须使用阿里云动态生成占位符。
        """

        try:

            params = json.loads(
                self._template_param
            )

        except (TypeError, ValueError) as exc:

            logger.error(
                "SMS_CONFIG_ERROR: "
                "TemplateParam 不是合法 JSON"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            ) from exc

        if not isinstance(params, dict):

            logger.error(
                "SMS_CONFIG_ERROR: "
                "TemplateParam 必须为 JSON 对象"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            )

        # 必须使用动态验证码
        if params.get("code") != "##code##":

            logger.error(
                "SMS_CONFIG_ERROR: "
                "模板 code 参数配置错误"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            )

        # 当前模板必须包含 min 参数
        if "min" not in params:

            logger.error(
                "SMS_CONFIG_ERROR: "
                "短信模板缺少 min 参数"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            )

        # 检查验证码有效时间
        if not isinstance(self._valid_time, int):

            logger.error(
                "SMS_CONFIG_ERROR: "
                "ValidTime 必须为整数"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            )

        if self._valid_time <= 0:

            logger.error(
                "SMS_CONFIG_ERROR: "
                "ValidTime 必须大于 0"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            )

        # 有效期采用整分钟
        if self._valid_time % 60 != 0:

            logger.error(
                "SMS_CONFIG_ERROR: "
                "验证码有效期必须为整分钟"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            )

        expected_min = str(
            self._valid_time // 60
        )

        # 短信显示的有效时间和 API 实际有效期保持一致
        if str(params["min"]) != expected_min:

            logger.error(
                "SMS_CONFIG_ERROR: "
                "模板有效时间与 ValidTime 不一致"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            )

        if not isinstance(self._code_length, int):

            logger.error(
                "SMS_CONFIG_ERROR: "
                "CodeLength 必须为整数"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            )

        if not 4 <= self._code_length <= 8:

            logger.error(
                "SMS_CONFIG_ERROR: "
                "CodeLength 必须为 4 至 8 位"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            )

        # 返回规范化后的 JSON 字符串
        return json.dumps(
            params,
            ensure_ascii=False,
            separators=(",", ":")
        )

    # ========================================================
    # 六、检查服务配置
    # ========================================================

    def _validate_config(self) -> None:
        """
        检查阿里云基础配置是否完整。
        """

        if (
            not self._access_key_id
            or not self._access_key_secret
        ):

            logger.error(
                "SMS_CONFIG_ERROR: "
                "阿里云 AccessKey 未配置"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            )

        if (
            not self._sign_name
            or not self._template_code
        ):

            logger.error(
                "SMS_CONFIG_ERROR: "
                "短信签名或模板编号未配置"
            )

            raise _to_business_error(
                "SMS_CONFIG_ERROR"
            )

    # ========================================================
    # 七、发送短信验证码
    # ========================================================

    async def send_code(
        self,
        phone: str
    ) -> Optional[str]:
        """
        发送短信验证码。

        返回：
            阿里云业务 ID（如有）。

        验证码由阿里云动态生成。
        """

        masked = mask_phone(phone)

        # 1. 检查基础配置
        self._validate_config()

        # 2. 检查短信模板参数
        template_param = (
            self._validate_template_param()
        )

        # 3. 初始化 SDK
        client, dypnsapi_models = (
            self._ensure_sdk()
        )

        # 4. 构造发送请求
        request = (
            dypnsapi_models
            .SendSmsVerifyCodeRequest(

                phone_number=phone,

                country_code=COUNTRY_CODE,

                sign_name=self._sign_name,

                template_code=self._template_code,

                template_param=template_param,

                # 纯数字验证码
                code_type=1,

                code_length=self._code_length,

                # 验证码有效期，单位：秒
                valid_time=self._valid_time,

                # 发送间隔，单位：秒
                interval=SEND_INTERVAL,

                # 同场景再次发送时覆盖旧验证码
                duplicate_policy=1,

                # 不返回验证码明文
                return_verify_code=False
            )
        )

        # 5. 调用阿里云接口
        try:

            response = (
                client.send_sms_verify_code(
                    request
                )
            )

        except Exception as exc:

            code = getattr(
                exc,
                "code",
                None
            )

            if _is_rate_limit(code):

                category = (
                    "ALIYUN_RATE_LIMIT"
                )

            elif code is None:

                category = (
                    "ALIYUN_NETWORK_ERROR"
                )

            else:

                category = (
                    "ALIYUN_API_ERROR"
                )

            logger.error(
                "SMS_SEND_ERROR "
                "category=%s "
                "phone=%s "
                "aliyun_code=%s "
                "request_id=%s",
                category,
                masked,
                code,
                _extract_request_id(exc)
            )

            raise _to_business_error(
                category,
                operation="send"
            ) from exc

        # 6. 检查接口响应
        body = getattr(
            response,
            "body",
            None
        )

        if body is None:

            logger.error(
                "SMS_SEND_ERROR "
                "category=ALIYUN_API_ERROR "
                "phone=%s "
                "reason=empty_response",
                masked
            )

            raise _to_business_error(
                "ALIYUN_API_ERROR",
                operation="send"
            )

        code = getattr(
            body,
            "code",
            None
        )

        success = getattr(
            body,
            "success",
            None
        )

        # 必须同时满足接口状态与执行状态
        if code != "OK" or success is not True:

            category = (
                "ALIYUN_RATE_LIMIT"
                if _is_rate_limit(code)
                else "ALIYUN_API_ERROR"
            )

            logger.error(
                "SMS_SEND_ERROR "
                "category=%s "
                "phone=%s "
                "aliyun_code=%s "
                "request_id=%s",
                category,
                masked,
                code,
                getattr(
                    body,
                    "request_id",
                    None
                )
            )

            raise _to_business_error(
                category,
                operation="send"
            )

        # 7. 发送请求成功
        logger.info(
            "SMS_SENT phone=%s",
            masked
        )

        model = getattr(
            body,
            "model",
            None
        )

        return getattr(
            model,
            "biz_id",
            None
        )

    # ========================================================
    # 八、核验短信验证码
    # ========================================================

    async def verify_code(
        self,
        phone: str,
        code: str
    ) -> bool:
        """
        核验短信验证码。

        只有：
            VerifyResult == PASS

        才返回 True。
        """

        masked = mask_phone(phone)

        # 1. 检查配置
        self._validate_config()

        # 2. 初始化 SDK
        client, dypnsapi_models = (
            self._ensure_sdk()
        )

        # 3. 构造核验请求
        request = (
            dypnsapi_models
            .CheckSmsVerifyCodeRequest(

                phone_number=phone,

                country_code=COUNTRY_CODE,

                verify_code=code
            )
        )

        # 4. 调用阿里云核验接口
        try:

            response = (
                client.check_sms_verify_code(
                    request
                )
            )

        except Exception as exc:

            api_code = getattr(
                exc,
                "code",
                None
            )

            if _is_rate_limit(api_code):

                category = (
                    "ALIYUN_RATE_LIMIT"
                )

            elif api_code is None:

                category = (
                    "ALIYUN_NETWORK_ERROR"
                )

            else:

                category = (
                    "ALIYUN_API_ERROR"
                )

            logger.error(
                "SMS_VERIFY_ERROR "
                "category=%s "
                "phone=%s "
                "aliyun_code=%s "
                "request_id=%s",
                category,
                masked,
                api_code,
                _extract_request_id(exc)
            )

            raise _to_business_error(
                category,
                operation="verify"
            ) from exc

        # 5. 检查接口响应
        body = getattr(
            response,
            "body",
            None
        )

        if body is None:

            logger.error(
                "SMS_VERIFY_ERROR "
                "category=ALIYUN_API_ERROR "
                "phone=%s "
                "reason=empty_response",
                masked
            )

            raise _to_business_error(
                "ALIYUN_API_ERROR",
                operation="verify"
            )

        api_code = getattr(
            body,
            "code",
            None
        )

        success = getattr(
            body,
            "success",
            None
        )

        if (
            api_code != "OK"
            or success is not True
        ):

            category = (
                "ALIYUN_RATE_LIMIT"
                if _is_rate_limit(api_code)
                else "ALIYUN_API_ERROR"
            )

            logger.error(
                "SMS_VERIFY_ERROR "
                "category=%s "
                "phone=%s "
                "aliyun_code=%s "
                "request_id=%s",
                category,
                masked,
                api_code,
                getattr(
                    body,
                    "request_id",
                    None
                )
            )

            raise _to_business_error(
                category,
                operation="verify"
            )

        # 6. 获取真实核验结果
        model = getattr(
            body,
            "model",
            None
        )

        verify_result = getattr(
            model,
            "verify_result",
            None
        )

        # 7. 只有 PASS 代表验证码正确
        if verify_result == "PASS":

            logger.info(
                "SMS_VERIFY_SUCCESS phone=%s",
                masked
            )

            return True

        logger.info(
            "SMS_VERIFY_FAILED phone=%s",
            masked
        )

        return False


# ============================================================
# 九、短信服务工厂
# ============================================================

def build_aliyun_provider() -> AliyunSMSProvider:
    """
    根据项目统一配置创建阿里云短信认证服务。

    保留现有工厂函数接口。
    """

    return AliyunSMSProvider(

        access_key_id=(
            settings.ALIYUN_ACCESS_KEY_ID
        ),

        access_key_secret=(
            settings.ALIYUN_ACCESS_KEY_SECRET
        ),

        sign_name=(
            settings.ALIYUN_SMS_SIGN_NAME
        ),

        template_code=(
            settings.ALIYUN_SMS_TEMPLATE_CODE
        ),

        endpoint=(
            settings.ALIYUN_SMS_ENDPOINT
        ),

        template_param=(
            settings.ALIYUN_SMS_TEMPLATE_PARAM
        ),

        code_length=(
            settings.ALIYUN_SMS_CODE_LENGTH
        ),

        valid_time=(
            settings.ALIYUN_SMS_VALID_TIME
        )
    )

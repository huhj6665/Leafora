"""ORM 模型统一导出.

在此处导入所有模型，确保 Alembic autogenerate 与 Base.metadata
能够收集到全部表结构。
"""
from app.models.device import Device, DeviceBinding
from app.models.email_credential import EmailCredential, EmailCredentialPurpose
from app.models.identity import IdentityType, UserIdentity
from app.models.field import Field
from app.models.inspection import (
    CloudDetection,
    DetectionRecord,
    DetectionResult,
    DeviceStatusRecord,
    EnvironmentRecord,
    ImageRecord,
    InspectionEvent,
    InspectionRecord,
    LocationRecord,
)
from app.models.profile import UserProfile
from app.models.protocol import DeviceControlRequest, DevicePairingSession, WebLoginSession
from app.models.task import DeviceLatestData, TaskCommand
from app.models.user import User
from app.models.assistant import (AssistantConversation, AssistantMessage, AssistantRun,
                                 AssistantEvent, AssistantDocument, AssistantFieldContext)

__all__ = [
    "AssistantConversation",
    "AssistantMessage",
    "AssistantRun",
    "AssistantEvent",
    "AssistantDocument",
    "AssistantFieldContext",
    "User",
    "UserIdentity",
    "IdentityType",
    "UserProfile",
    "EmailCredential",
    "EmailCredentialPurpose",
    "Device",
    "DeviceBinding",
    "Field",
    "InspectionRecord",
    "InspectionEvent",
    "LocationRecord",
    "EnvironmentRecord",
    "DeviceStatusRecord",
    "DetectionRecord",
    "DetectionResult",
    "ImageRecord",
    "CloudDetection",
    "DevicePairingSession",
    "WebLoginSession",
    "DeviceControlRequest",
    "TaskCommand",
    "DeviceLatestData",
]

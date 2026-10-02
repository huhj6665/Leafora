from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Context(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_id: str | None = Field(None, max_length=64)
    inspection_id: str | None = Field(None, max_length=64)
    crop: str = Field("烟草", max_length=40)
    variety: str = Field("", max_length=60)
    growth_stage: str = Field("", max_length=60)
    location: str = Field("", max_length=100)


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field("新的对话", min_length=1, max_length=100)
    context: Context = Field(default_factory=Context)


class ConversationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, min_length=1, max_length=100)
    context: Context | None = None


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=4000)
    client_request_id: str = Field(min_length=8, max_length=64)
    attachment_ids: list[str] = Field(default_factory=list, max_length=8)
    web_enabled: bool = True
    image_enabled: bool = False
    context: Context | None = None
    regenerate_message_id: str | None = Field(None, max_length=40)


class FieldContextUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    crop: str = Field("烟草", max_length=40)
    variety: str = Field("", max_length=60)
    growth_stage: str = Field("", max_length=60)
    location: str = Field("", max_length=100)

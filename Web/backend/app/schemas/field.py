"""Field management request schemas."""
from typing import Optional

from pydantic import BaseModel, Field as PydanticField


class FieldCreate(BaseModel):
    name: str = PydanticField(..., min_length=1, max_length=128)
    description: Optional[str] = PydanticField(default=None, max_length=500)
    pixel_boundary: list[list[float]]
    image_width: int = PydanticField(..., gt=0)
    image_height: int = PydanticField(..., gt=0)
    origin_longitude: float
    origin_latitude: float
    longitude_per_pixel: float
    latitude_per_pixel: float


class FieldUpdate(BaseModel):
    name: Optional[str] = PydanticField(default=None, min_length=1, max_length=128)
    description: Optional[str] = PydanticField(default=None, max_length=500)
    status: Optional[str] = PydanticField(default=None, pattern="^(READY|DISABLED)$")
    pixel_boundary: Optional[list[list[float]]] = None

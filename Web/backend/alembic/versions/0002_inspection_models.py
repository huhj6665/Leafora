"""inspection data models

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22

新增巡检业务表：
    inspection_records / location_records / environment_records
    device_status_records / detection_records / detection_results
    images / cloud_detection
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type():
    """跨数据库 JSON 列类型（PostgreSQL JSON / SQLite JSON）."""
    return sa.JSON()


def upgrade() -> None:
    # ---------------- inspection_records 巡检记录主表 ----------------
    op.create_table(
        "inspection_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="记录主键ID"),
        sa.Column("device_id", sa.String(length=64), nullable=False, comment="设备编号，如 TLD_SIM_001"),
        sa.Column("data_id", sa.String(length=64), nullable=False, comment="巡检数据唯一ID（UUID4）"),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True, comment="归属用户ID（由后端根据绑定关系确定）"),
        sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="1.0", comment="MQTT 协议版本"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, comment="设备采集时间（timestamp）"),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="服务端接收/入库时间"),
        sa.Column("raw_payload", sa.Text(), nullable=True, comment="原始 MQTT JSON 字符串"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "data_id", name="uq_inspection_device_data"),
    )
    op.create_index("ix_inspection_device_id", "inspection_records", ["device_id"])
    op.create_index("ix_inspection_owner_user_id", "inspection_records", ["owner_user_id"])

    # ---------------- location_records 定位数据 ----------------
    op.create_table(
        "location_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("inspection_id", sa.BigInteger(), nullable=False, comment="关联巡检记录ID"),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("altitude_msl_m", sa.Float(), nullable=False),
        sa.Column("height_ellipsoid_m", sa.Float(), nullable=False),
        sa.Column("fix_quality", sa.Integer(), nullable=False),
        sa.Column("rtk_status", sa.String(length=16), nullable=False),
        sa.Column("satellites_used", sa.Integer(), nullable=False),
        sa.Column("horizontal_accuracy_m", sa.Float(), nullable=False),
        sa.Column("vertical_accuracy_m", sa.Float(), nullable=False),
        sa.Column("ground_speed_mps", sa.Float(), nullable=False),
        sa.Column("course_over_ground_deg", sa.Float(), nullable=False),
        sa.Column("correction_age_s", sa.Float(), nullable=False),
        sa.Column("position_valid", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspection_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inspection_id"),
    )
    op.create_index("ix_location_records_inspection_id", "location_records", ["inspection_id"])

    # ---------------- environment_records 环境数据 ----------------
    op.create_table(
        "environment_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("inspection_id", sa.BigInteger(), nullable=False, comment="关联巡检记录ID"),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("humidity", sa.Float(), nullable=False),
        sa.Column("co2", sa.Float(), nullable=False),
        sa.Column("light", sa.Float(), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False, comment="环境采样时间"),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspection_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inspection_id"),
    )
    op.create_index("ix_environment_records_inspection_id", "environment_records", ["inspection_id"])

    # ---------------- device_status_records 设备状态 ----------------
    op.create_table(
        "device_status_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("inspection_id", sa.BigInteger(), nullable=False, comment="关联巡检记录ID"),
        sa.Column("cpu_usage", sa.Float(), nullable=False),
        sa.Column("memory_usage", sa.Float(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspection_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inspection_id"),
    )
    op.create_index("ix_device_status_records_inspection_id", "device_status_records", ["inspection_id"])

    # ---------------- detection_records Jetson 检测 ----------------
    op.create_table(
        "detection_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("inspection_id", sa.BigInteger(), nullable=False, comment="关联巡检记录ID"),
        sa.Column("has_target", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspection_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inspection_id"),
    )
    op.create_index("ix_detection_records_inspection_id", "detection_records", ["inspection_id"])

    # ---------------- detection_results 检测明细 ----------------
    op.create_table(
        "detection_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("detection_id", sa.BigInteger(), nullable=False, comment="关联 detection_records.id"),
        sa.Column("class_name", sa.String(length=64), nullable=False, comment="类别"),
        sa.Column("confidence", sa.Float(), nullable=False, comment="置信度"),
        sa.Column("bbox", _json_type(), nullable=False, comment="[x1,y1,x2,y2]"),
        sa.ForeignKeyConstraint(["detection_id"], ["detection_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detection_results_detection_id", "detection_results", ["detection_id"])

    # ---------------- images 图片 ----------------
    op.create_table(
        "images",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("image_id", sa.String(length=64), nullable=False, comment="图片唯一ID（UUID4）"),
        sa.Column("inspection_id", sa.BigInteger(), nullable=False, comment="关联巡检记录ID"),
        sa.Column("image_type", sa.String(length=16), nullable=False, server_default="original", comment="original / annotated"),
        sa.Column("storage_key", sa.String(length=512), nullable=False, comment="相对存储路径（storage key）"),
        sa.Column("content_type", sa.String(length=64), nullable=True, comment="MIME 类型"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upload_status", sa.String(length=32), nullable=False, server_default="completed", comment="上传状态"),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspection_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("image_id"),
    )
    op.create_index("ix_images_inspection_id", "images", ["inspection_id"])

    # ---------------- cloud_detection 云端检测 ----------------
    op.create_table(
        "cloud_detection",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("image_id", sa.BigInteger(), nullable=False, comment="关联 images.id（一对一）"),
        sa.Column("inspection_id", sa.BigInteger(), nullable=False, comment="关联巡检记录ID"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending", comment="推理任务状态"),
        sa.Column("model_name", sa.String(length=64), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("weights_identifier", sa.String(length=128), nullable=True, comment="权重标识（SHA-256 / 文件名）"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True, comment="模型处理完成时间"),
        sa.Column("has_target", sa.Boolean(), nullable=True),
        sa.Column("results", _json_type(), nullable=True, comment='[{class, confidence, bbox}]'),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspection_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("image_id"),
    )
    op.create_index("ix_cloud_detection_image_id", "cloud_detection", ["image_id"])
    op.create_index("ix_cloud_detection_inspection_id", "cloud_detection", ["inspection_id"])


def downgrade() -> None:
    op.drop_table("cloud_detection")
    op.drop_table("images")
    op.drop_table("detection_results")
    op.drop_table("detection_records")
    op.drop_table("device_status_records")
    op.drop_table("environment_records")
    op.drop_table("location_records")
    op.drop_table("inspection_records")

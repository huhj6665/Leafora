"""V0.3 END evidence, independent of a device's previous heartbeat."""
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models.inspection import InspectionEvent, InspectionRecord
from app.models.task import TaskCommand

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def stopped_summary(payload):
    summary = (payload or {}).get("summary")
    if not isinstance(summary, dict) or summary.get("sampling_stopped") is not True:
        return None
    for key in ("sample_count", "pending_sync_count"):
        if type(summary.get(key)) is not int or summary[key] < 0:
            return None
    if summary["sample_count"] == 0:
        if ("last_data_id" not in summary or "last_sequence" not in summary
                or summary["last_data_id"] is not None or summary["last_sequence"] is not None):
            return None
    elif (not isinstance(summary.get("last_data_id"), str) or not summary["last_data_id"]
          or type(summary.get("last_sequence")) is not int or summary["last_sequence"] < 0):
        return None
    return summary


async def try_complete(session, command, event):
    """Call while holding the END command lock; no historical data is rewritten."""
    accepted = stopped_summary(command.accepted_ack_payload)
    final = stopped_summary(command.final_ack_payload)
    if (event.status in TERMINAL or command.status != "ACCEPTED" or not accepted or not final
            or final["pending_sync_count"] != 0):
        return False
    if any(accepted[key] != final[key] for key in (
        "sampling_stopped", "last_data_id", "last_sequence", "sample_count"
    )):
        return False
    conditions = [InspectionRecord.event_id == event.id,
                  InspectionRecord.device_id == event.device_id,
                  InspectionRecord.owner_user_id == event.owner_user_id]
    count, sequences, max_sequence = (await session.execute(select(
        func.count(InspectionRecord.id), func.count(func.distinct(InspectionRecord.sequence)),
        func.max(InspectionRecord.sequence),
    ).where(*conditions))).one()
    if count != final["sample_count"]:
        return False
    if count:
        last = await session.scalar(select(InspectionRecord.id).where(
            *conditions, InspectionRecord.data_id == final["last_data_id"],
            InspectionRecord.sequence == final["last_sequence"],
        ))
        if last is None or sequences != count or max_sequence != final["last_sequence"]:
            return False
    event.status, event.sync_status, event.pending_sync_count = "COMPLETED", "SYNCED", 0
    event.ended_at = datetime.now(timezone.utc)
    command.status = "COMPLETED"
    command.ack_payload = command.final_ack_payload
    return True


async def recheck_after_data(session, event_id):
    command = await session.scalar(select(TaskCommand).where(
        TaskCommand.inspection_pk == event_id, TaskCommand.command_type == "END_INSPECTION",
        TaskCommand.status == "ACCEPTED",
    ).with_for_update().execution_options(populate_existing=True))
    if command is not None:
        event = await session.scalar(select(InspectionEvent).where(
            InspectionEvent.id == event_id,
        ).with_for_update().execution_options(populate_existing=True))
        await try_complete(session, command, event)

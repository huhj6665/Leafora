"""Event listing keeps relationship loading constant per page."""
from sqlalchemy import event as sqlalchemy_event

from app.services import event_service, inspection_service
from tests.helpers import make_device, make_user, valid_payload


async def test_event_list_batches_records_for_the_page(session_factory):
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, owner_user_id=user.id)
        for index in range(4):
            created = await event_service.create_event(
                db, user.id, "TLD_SIM_001", f"批量查询 {index}", None
            )
            payload = valid_payload(data_id=f"batch-event-{index}")
            payload["inspection_id"] = created["inspection_id"]
            await inspection_service.ingest_message(
                db, payload, "tld/device/TLD_SIM_001/data"
            )

        statements = 0

        def count_statement(*_args):
            nonlocal statements
            statements += 1

        engine = db.bind
        sqlalchemy_event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
        try:
            result = await event_service.list_events(db, user.id, page=1, page_size=20)
        finally:
            sqlalchemy_event.remove(engine.sync_engine, "before_cursor_execute", count_statement)

        assert result["total"] == 4
        assert len(result["items"]) == 4
        assert all(item["sample_count"] == 1 for item in result["items"])
        assert all(item["target_count"] == 1 for item in result["items"])
        # count + page + one batched relationship graph, independent of event count
        assert statements == 6

"""Quiet DB sessions for private assistant content, without changing business logging."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.core.config import settings
from app.database.session import engine as business_engine, get_db

engine = create_async_engine(settings.DATABASE_URL, echo=False, hide_parameters=True, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_assistant_db(db=Depends(get_db)):
    # Preserve get_db dependency overrides used by isolated tests.
    if db.bind is not business_engine:
        yield db
    else:
        async with AsyncSessionLocal() as private_session:
            yield private_session

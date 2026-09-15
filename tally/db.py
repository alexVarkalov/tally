from __future__ import annotations

import asyncio

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from tally.persistence import BotUser, Tracker
from tally.persistence.models import Base
from tally.persistence.trackers import TrackerStore
from tally.persistence.users import UserStore

__all__ = ["BotUser", "Database", "Tracker"]


class Database(UserStore, TrackerStore):
    """PostgreSQL persistence via SQLAlchemy ORM; public methods stay async."""

    def __init__(self, url: str) -> None:
        self._engine: Engine = create_engine(url, future=True)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False, class_=Session)

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        Base.metadata.create_all(self._engine)
        # Additive migrations only (playbook §3.7): ALTER TABLE ... ADD COLUMN IF NOT EXISTS, never drop/rename.
        with self._engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_locale VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR"))

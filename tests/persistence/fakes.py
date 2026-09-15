from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass
class FakeSession:
    scalar_results: list[Any] = field(default_factory=list)
    scalars_results: list[list[Any]] = field(default_factory=list)
    executed: list[Any] = field(default_factory=list)
    added: list[Any] = field(default_factory=list)
    deleted: list[Any] = field(default_factory=list)
    committed: int = 0
    execute_rowcount: int = 1

    def execute(self, stmt: Any) -> Any:
        self.executed.append(stmt)
        row = SimpleNamespace(id=1) if self.execute_rowcount > 0 else None
        return SimpleNamespace(rowcount=self.execute_rowcount, first=lambda: row)

    def scalar(self, _stmt: Any) -> Any:
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def scalars(self, _stmt: Any) -> Any:
        rows = self.scalars_results.pop(0) if self.scalars_results else []
        return SimpleNamespace(all=lambda: rows)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    def commit(self) -> None:
        self.committed += 1


class FakeSessionFactory:
    def __init__(self, session: FakeSession):
        self._session = session

    def __call__(self) -> FakeSessionFactory:
        return self

    def __enter__(self) -> FakeSession:
        return self._session

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None


class FakeInsert:
    def __init__(self) -> None:
        self.excluded = SimpleNamespace(
            username="ex_username",
            first_name="ex_first_name",
            last_name="ex_last_name",
            language_code="ex_language_code",
            target_text="ex_target_text",
            ease_factor=2.5,
            interval_days=1.0,
            repetition=1,
            next_review_at="ex_next_review_at",
        )

    def values(self, **_kwargs: Any) -> FakeInsert:
        return self

    def on_conflict_do_update(self, **_kwargs: Any) -> FakeInsert:
        return self

    def on_conflict_do_nothing(self, **_kwargs: Any) -> FakeInsert:
        return self

    def returning(self, *_args: Any) -> FakeInsert:
        return self

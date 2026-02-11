from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite
import asyncpg

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DatabaseDsn:
    driver: str
    value: str


def parse_database_dsn(url: str) -> DatabaseDsn:
    if url.startswith("sqlite:///"):
        return DatabaseDsn(driver="sqlite", value=url.replace("sqlite:///", "", 1))
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return DatabaseDsn(driver="postgresql", value=url)
    raise ValueError("Unsupported database URL. Use sqlite:/// or postgresql://")


def _qmark_to_dollar(query: str) -> str:
    idx = 1
    out: list[str] = []
    for char in query:
        if char == "?":
            out.append(f"${idx}")
            idx += 1
        else:
            out.append(char)
    return "".join(out)


class Database:
    def __init__(self, url: str, timeout_seconds: int = 30, pool_min_size: int = 2, pool_max_size: int = 10) -> None:
        self._dsn = parse_database_dsn(url)
        self._timeout_seconds = timeout_seconds
        self._pool_min_size = pool_min_size
        self._pool_max_size = pool_max_size
        self._sqlite: aiosqlite.Connection | None = None
        self._pg_pool: asyncpg.Pool | None = None
        self._sqlite_lock = asyncio.Lock()

    @property
    def driver(self) -> str:
        return self._dsn.driver

    async def connect(self) -> None:
        if self.driver == "sqlite":
            sqlite_path = Path(self._dsn.value)
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._sqlite = await aiosqlite.connect(sqlite_path)
            self._sqlite.row_factory = aiosqlite.Row
            await self._sqlite.execute("PRAGMA journal_mode = WAL;")
            await self._sqlite.execute("PRAGMA foreign_keys = ON;")
            await self._sqlite.commit()
            LOGGER.info("Connected to SQLite: %s", sqlite_path)
            return
        self._pg_pool = await asyncpg.create_pool(
            dsn=self._dsn.value,
            min_size=self._pool_min_size,
            max_size=self._pool_max_size,
            timeout=self._timeout_seconds,
        )
        LOGGER.info("Connected to PostgreSQL")

    async def close(self) -> None:
        if self._sqlite:
            await self._sqlite.close()
            self._sqlite = None
        if self._pg_pool:
            await self._pg_pool.close()
            self._pg_pool = None

    async def execute(self, query: str, params: Sequence[Any] | None = None) -> str:
        params = params or []
        if self.driver == "sqlite":
            assert self._sqlite is not None
            async with self._sqlite_lock:
                await self._sqlite.execute(query, tuple(params))
                await self._sqlite.commit()
            return "OK"

        assert self._pg_pool is not None
        converted = _qmark_to_dollar(query)
        async with self._pg_pool.acquire() as conn:
            return await conn.execute(converted, *params)

    async def executemany(self, query: str, rows: Sequence[Sequence[Any]]) -> None:
        if not rows:
            return
        if self.driver == "sqlite":
            assert self._sqlite is not None
            async with self._sqlite_lock:
                await self._sqlite.executemany(query, rows)
                await self._sqlite.commit()
            return

        assert self._pg_pool is not None
        converted = _qmark_to_dollar(query)
        async with self._pg_pool.acquire() as conn:
            await conn.executemany(converted, rows)

    async def fetchone(self, query: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
        params = params or []
        if self.driver == "sqlite":
            assert self._sqlite is not None
            async with self._sqlite_lock:
                cursor = await self._sqlite.execute(query, tuple(params))
                row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

        assert self._pg_pool is not None
        converted = _qmark_to_dollar(query)
        async with self._pg_pool.acquire() as conn:
            row = await conn.fetchrow(converted, *params)
        if row is None:
            return None
        return dict(row)

    async def fetchall(self, query: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        params = params or []
        if self.driver == "sqlite":
            assert self._sqlite is not None
            async with self._sqlite_lock:
                cursor = await self._sqlite.execute(query, tuple(params))
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]

        assert self._pg_pool is not None
        converted = _qmark_to_dollar(query)
        async with self._pg_pool.acquire() as conn:
            rows = await conn.fetch(converted, *params)
        return [dict(row) for row in rows]

    async def executescript(self, sql_script: str) -> None:
        if self.driver == "sqlite":
            assert self._sqlite is not None
            async with self._sqlite_lock:
                await self._sqlite.executescript(sql_script)
                await self._sqlite.commit()
            return

        assert self._pg_pool is not None
        async with self._pg_pool.acquire() as conn:
            await conn.execute(sql_script)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        if self.driver == "sqlite":
            async with self._sqlite_lock:
                try:
                    assert self._sqlite is not None
                    await self._sqlite.execute("BEGIN")
                    yield
                    await self._sqlite.commit()
                except Exception:
                    await self._sqlite.rollback()
                    raise
            return

        assert self._pg_pool is not None
        async with self._pg_pool.acquire() as conn:
            async with conn.transaction():
                yield

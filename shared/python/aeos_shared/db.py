"""Shared database connection pool and helpers for AEOS services."""

import os
import logging
import asyncpg
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

import json

_pool: asyncpg.Pool | None = None

async def _init_connection(conn):
    """Set up codecs for json and jsonb"""
    await conn.set_type_codec(
        'json', encoder=json.dumps, decoder=json.loads, schema='pg_catalog'
    )
    await conn.set_type_codec(
        'jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog'
    )

async def init_db_pool() -> asyncpg.Pool:
    """Initialize the global asyncpg connection pool."""
    global _pool
    if _pool is None:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            raise RuntimeError("DATABASE_URL environment variable is not set.")
        logger.info("Initializing asyncpg connection pool...")
        _pool = await asyncpg.create_pool(db_url, init=_init_connection)
    return _pool

async def close_db_pool():
    """Close the global asyncpg connection pool."""
    global _pool
    if _pool is not None:
        logger.info("Closing asyncpg connection pool...")
        await _pool.close()
        _pool = None

async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    """FastAPI Dependency: Acquire a database connection from the pool."""
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        yield conn

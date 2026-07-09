"""Shared database connection pool and helpers for AEOS services."""

import os
import logging
import asyncpg
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

import json

_pool: asyncpg.Pool | None = None
_read_pool: asyncpg.Pool | None = None

async def _init_connection(conn):
    """Set up codecs for json and jsonb"""
    await conn.set_type_codec(
        'json', encoder=json.dumps, decoder=json.loads, schema='pg_catalog'
    )
    await conn.set_type_codec(
        'jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog'
    )

async def init_db_pool() -> asyncpg.Pool:
    """Initialize the global asyncpg connection pools."""
    global _pool, _read_pool
    if _pool is None:
        db_url = os.environ.get("DATABASE_URL")
        replica_url = os.environ.get("DATABASE_REPLICA_URL", db_url)
        if not db_url:
            raise RuntimeError("DATABASE_URL environment variable is not set.")
        logger.info("Initializing asyncpg connection pool (Primary)...")
        _pool = await asyncpg.create_pool(db_url, init=_init_connection)
        
        logger.info("Initializing asyncpg connection pool (Replica)...")
        _read_pool = await asyncpg.create_pool(replica_url, init=_init_connection)
    return _pool

async def close_db_pool():
    """Close the global asyncpg connection pools."""
    global _pool, _read_pool
    if _pool is not None:
        logger.info("Closing asyncpg connection pools...")
        await _pool.close()
        _pool = None
    if _read_pool is not None:
        await _read_pool.close()
        _read_pool = None

async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    """FastAPI Dependency: Acquire a primary database connection from the pool."""
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        yield conn

async def get_db_read() -> AsyncGenerator[asyncpg.Connection, None]:
    """FastAPI Dependency: Acquire a read-replica database connection."""
    await init_db_pool()
    global _read_pool
    async with _read_pool.acquire() as conn:
        yield conn

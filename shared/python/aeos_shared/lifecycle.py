import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Callable, Awaitable, Optional
from fastapi import FastAPI
from .db import init_db_pool, close_db_pool

logger = logging.getLogger("aeos.lifecycle")

def create_graceful_lifespan(
    startup_func: Optional[Callable[[], Awaitable[None]]] = None,
    shutdown_func: Optional[Callable[[], Awaitable[None]]] = None
):
    @asynccontextmanager
    async def graceful_lifespan(app: FastAPI):
        # Default AEOS Shared Startup
        try:
            await init_db_pool()
        except Exception as e:
            logger.warning(f"Database pool initialization skipped or failed: {e}")
            
        # Service-specific startup
        if startup_func:
            try:
                await startup_func()
            except Exception as e:
                logger.error(f"Service startup function failed: {e}")

        yield
        
        # Shutdown phase: Connection Draining
        logger.info("SIGTERM received. Starting graceful shutdown sequence...")
        logger.info("Waiting 5 seconds for in-flight requests to drain and load balancers to update...")
        await asyncio.sleep(5)
        
        # Service-specific shutdown
        if shutdown_func:
            try:
                await shutdown_func()
            except Exception as e:
                logger.error(f"Service shutdown function failed: {e}")

        # Default AEOS Shared Shutdown
        logger.info("Draining complete. Closing database connections...")
        try:
            await close_db_pool()
        except Exception as e:
            logger.warning(f"Error closing database pool: {e}")
        
        logger.info("Graceful shutdown complete.")

    return graceful_lifespan

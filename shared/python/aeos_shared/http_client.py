import asyncio
import logging
import time
from typing import Optional, Dict, Any, Callable
import httpx

logger = logging.getLogger(__name__)

class CircuitBreakerOpenException(Exception):
    pass

class CircuitBreaker:
    """A lightweight Circuit Breaker to prevent cascading failures."""
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_failure_time = 0.0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit Breaker tripped OPEN after {self.failure_count} failures.")

    def record_success(self):
        if self.state != "CLOSED":
            logger.info("Circuit Breaker reset to CLOSED.")
        self.state = "CLOSED"
        self.failure_count = 0

    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit Breaker transitioning to HALF_OPEN state.")
                return True
            return False
        if self.state == "HALF_OPEN":
            # Only allow one test request through in half-open state
            return True
        return False

# Global circuit breakers per host to prevent noisy neighbors
_circuit_breakers: Dict[str, CircuitBreaker] = {}

def get_circuit_breaker(host: str) -> CircuitBreaker:
    if host not in _circuit_breakers:
        _circuit_breakers[host] = CircuitBreaker()
    return _circuit_breakers[host]

async def request_with_retry(
    method: str, 
    url: str, 
    max_retries: int = 3, 
    base_delay: float = 1.0, 
    **kwargs
) -> httpx.Response:
    """
    Executes an HTTP request with exponential backoff and circuit breaking.
    """
    parsed_url = httpx.URL(url)
    host = parsed_url.host
    breaker = get_circuit_breaker(host)

    if not breaker.can_execute():
        raise CircuitBreakerOpenException(f"Circuit Breaker is OPEN for {host}")

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                breaker.record_success()
                return response
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500 and e.response.status_code != 429:
                # Client errors (4xx) except Too Many Requests shouldn't trip the breaker
                breaker.record_success()
                raise e
            logger.warning(f"Request failed to {url} (status={e.response.status_code}). Attempt {attempt + 1}/{max_retries}")
        except httpx.RequestError as e:
            logger.warning(f"Network error to {url} ({e}). Attempt {attempt + 1}/{max_retries}")

        # If it's the last attempt, don't sleep, just record failure
        if attempt == max_retries - 1:
            breaker.record_failure()
            raise httpx.RequestError(f"Max retries ({max_retries}) exceeded for {url}") from None

        # Exponential backoff with jitter
        sleep_time = base_delay * (2 ** attempt)
        await asyncio.sleep(sleep_time)

    # Should not reach here
    raise Exception("Unexpected error in request_with_retry")

async def post(url: str, **kwargs) -> httpx.Response:
    return await request_with_retry("POST", url, **kwargs)

async def get(url: str, **kwargs) -> httpx.Response:
    return await request_with_retry("GET", url, **kwargs)

async def put(url: str, **kwargs) -> httpx.Response:
    return await request_with_retry("PUT", url, **kwargs)

async def delete(url: str, **kwargs) -> httpx.Response:
    return await request_with_retry("DELETE", url, **kwargs)

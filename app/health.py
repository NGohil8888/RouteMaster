"""Background health monitoring for Ollama Cloud accounts."""

import asyncio
import logging
import time
from typing import List

import httpx

from app.config import settings
from app.account_manager import AccountState, get_account_pool
from app.models import HealthCheckResult

logger = logging.getLogger(__name__)


async def check_account_health(index: int) -> HealthCheckResult:
    """Check the health of a single Ollama Cloud account."""
    account_pool = get_account_pool()
    if account_pool is None:
        return HealthCheckResult(
            index=index,
            healthy=False,
            state=AccountState.UNKNOWN,
            error="Pool not initialized",
        )

    account = account_pool.get_account_by_index(index)
    if account is None:
        return HealthCheckResult(
            index=index,
            healthy=False,
            state=AccountState.UNKNOWN,
            error="Account not found",
        )

    url = f"{settings.ollama_openai_base}/models"
    headers = {"Authorization": f"Bearer {account.api_key}"}

    start_time = time.time()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.health_check_timeout_seconds)
        ) as client:
            response = await client.get(url, headers=headers)

        response_time_ms = (time.time() - start_time) * 1000

        if response.status_code == 200:
            logger.debug(
                f"Health check passed for account {index} "
                f"({response_time_ms:.1f}ms)"
            )
            if account.status.state != AccountState.HEALTHY:
                await account_pool.update_account_state(index, AccountState.HEALTHY)
            return HealthCheckResult(
                index=index,
                healthy=True,
                state=AccountState.HEALTHY,
                response_time_ms=response_time_ms,
                model_available=True,
            )

        error_msg = f"HTTP {response.status_code}"
        try:
            data = response.json()
            if "error" in data:
                err = data["error"]
                error_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        except Exception:
            pass

        if response.status_code == 429:
            state = AccountState.RATE_LIMITED
        elif response.status_code in (401, 403):
            state = AccountState.AUTH_ERROR
        else:
            state = AccountState.TEMPORARILY_UNAVAILABLE

        await account_pool.update_account_state(index, state, error=error_msg)
        return HealthCheckResult(
            index=index,
            healthy=False,
            state=state,
            response_time_ms=response_time_ms,
            error=error_msg,
        )

    except httpx.TimeoutException:
        await account_pool.update_account_state(
            index, AccountState.TEMPORARILY_UNAVAILABLE, error="Health check timeout"
        )
        return HealthCheckResult(
            index=index,
            healthy=False,
            state=AccountState.TEMPORARILY_UNAVAILABLE,
            error="Timeout",
        )

    except httpx.ConnectError as e:
        await account_pool.update_account_state(
            index, AccountState.TEMPORARILY_UNAVAILABLE, error=f"Connection error: {str(e)}"
        )
        return HealthCheckResult(
            index=index,
            healthy=False,
            state=AccountState.TEMPORARILY_UNAVAILABLE,
            error=f"Connection error: {str(e)}",
        )

    except Exception as e:
        await account_pool.update_account_state(
            index, AccountState.TEMPORARILY_UNAVAILABLE, error=f"Health check error: {str(e)}"
        )
        return HealthCheckResult(
            index=index,
            healthy=False,
            state=AccountState.TEMPORARILY_UNAVAILABLE,
            error=str(e),
        )


async def run_health_checks():
    """Run health checks for all accounts."""
    account_pool = get_account_pool()
    if account_pool is None:
        return []

    tasks = [
        check_account_health(i) for i in range(account_pool.total_accounts)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results


async def health_monitor_loop():
    """Background task that continuously monitors account health."""
    logger.info("Health monitor started")

    while True:
        try:
            results = await run_health_checks()
            healthy_count = sum(1 for r in results if isinstance(r, HealthCheckResult) and r.healthy)
            total = len(results)
            logger.info(f"Health check complete: {healthy_count}/{total} accounts healthy")

            for result in results:
                if isinstance(result, HealthCheckResult) and not result.healthy:
                    logger.warning(
                        f"Account {result.index} unhealthy: {result.state.value} - {result.error}"
                    )

        except Exception as e:
            logger.error(f"Health monitor error: {e}")

        await asyncio.sleep(settings.health_check_interval_seconds)
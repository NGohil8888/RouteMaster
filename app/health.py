"""Background health monitoring for Ollama Cloud API accounts."""

import asyncio
import logging

import httpx

from app.account_manager import AccountManager
from app.config import Settings

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Periodically checks the health of all configured accounts."""

    def __init__(self, account_manager: AccountManager, settings: Settings) -> None:
        self.account_manager = account_manager
        self.settings = settings
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the background health check loop."""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the background health check loop."""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        """Main loop."""
        await asyncio.sleep(2)
        while not self._stop_event.is_set():
            try:
                await self._check_all()
            except Exception:
                logger.exception("Health check round failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.settings.health_check_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

    async def _check_all(self) -> None:
        """Check every account concurrently."""
        accounts = self.account_manager.accounts
        if not accounts:
            return

        logger.debug("Starting health check round for %d accounts", len(accounts))
        await asyncio.gather(*(self._check_one(acc) for acc in accounts))

    async def _check_one(self, account) -> None:
        """Check a single account by listing models."""
        if account.state.cooldown_until:
            from datetime import datetime, timezone

            if datetime.now(timezone.utc) < account.state.cooldown_until:
                return

        url = f"{self.settings.ollama_api_base}/models"
        headers = {
            "Authorization": f"Bearer {account.api_key}",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            await self.account_manager.mark_unhealthy(account, "Health check timeout")
            return
        except Exception as exc:
            await self.account_manager.mark_unhealthy(account, f"Health check error: {exc}")
            return

        if response.status_code == 200:
            await self.account_manager.mark_healthy(account)
            logger.debug("Account %d health check passed", account.index)
        elif response.status_code in (401, 403):
            await self.account_manager.mark_failure(
                account, status_code=response.status_code, error_message="Invalid API key"
            )
        else:
            await self.account_manager.mark_unhealthy(
                account, f"HTTP {response.status_code}"
            )
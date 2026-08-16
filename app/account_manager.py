"""Thread-safe account pool with health-aware round-robin selection."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.config import Settings
from app.models import AccountState, AccountStatus

logger = logging.getLogger(__name__)


@dataclass
class Account:
    """Internal account representation."""

    index: int
    api_key: str
    state: AccountState = field(default_factory=lambda: AccountState(index=0, api_key_preview=""))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class AccountManager:
    """Manages a pool of Ollama Cloud API accounts with failover support."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._accounts: List[Account] = []
        self._round_robin_index: int = -1
        self._global_lock = asyncio.Lock()
        self._init_accounts()

    def _init_accounts(self) -> None:
        keys = self.settings.api_keys_list
        if not keys:
            logger.warning("No OLLAMA_API_KEYS configured. Gateway will not function.")
            return

        for idx, key in enumerate(keys):
            preview = f"{key[:4]}...{key[-4:]}" if len(key) >= 8 else "****"
            account = Account(
                index=idx,
                api_key=key,
                state=AccountState(
                    index=idx,
                    api_key_preview=preview,
                    status=AccountStatus.UNKNOWN,
                ),
            )
            self._accounts.append(account)
            logger.info("Registered Ollama account %d (%s)", idx, preview)

    @property
    def accounts(self) -> List[Account]:
        return self._accounts

    def _is_available(self, account: Account) -> bool:
        """Check if account is currently usable (not in cooldown, not disabled)."""
        if account.state.status == AccountStatus.DISABLED:
            return False
        if account.state.cooldown_until:
            if datetime.now(timezone.utc) < account.state.cooldown_until:
                return False
            # Cooldown expired; mark for re-evaluation
            account.state.cooldown_until = None
            account.state.status = AccountStatus.UNKNOWN
        return account.state.status in (
            AccountStatus.HEALTHY,
            AccountStatus.UNKNOWN,
        )

    async def get_next_available_account(self) -> Optional[Account]:
        """Select the next healthy account using round-robin."""
        async with self._global_lock:
            if not self._accounts:
                return None

            for _ in range(len(self._accounts)):
                self._round_robin_index = (self._round_robin_index + 1) % len(self._accounts)
                candidate = self._accounts[self._round_robin_index]
                if self._is_available(candidate):
                    return candidate

            return None

    async def mark_success(self, account: Account) -> None:
        """Mark an account as having served a successful request."""
        async with account.lock:
            account.state.status = AccountStatus.HEALTHY
            account.state.request_count += 1
            account.state.success_count += 1
            account.state.consecutive_failures = 0
            account.state.last_error = None
            account.state.last_status_code = None

    async def mark_failure(
        self,
        account: Account,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Mark an account as having failed a request, applying cooldown if needed."""
        async with account.lock:
            account.state.request_count += 1
            account.state.failure_count += 1
            account.state.consecutive_failures += 1
            account.state.last_status_code = status_code
            account.state.last_error = error_message

            # Determine new status and cooldown based on error type
            new_status, cooldown_seconds = self._classify_error(status_code, error_message)

            if new_status == AccountStatus.AUTH_ERROR:
                cooldown_seconds = cooldown_seconds or self.settings.account_cooldown_seconds * 5
            elif new_status == AccountStatus.RATE_LIMITED:
                cooldown_seconds = cooldown_seconds or self.settings.account_cooldown_seconds
            elif new_status == AccountStatus.TOKEN_EXHAUSTED:
                cooldown_seconds = cooldown_seconds or self.settings.account_cooldown_seconds * 3
            elif status_code and status_code >= 500:
                cooldown_seconds = cooldown_seconds or self.settings.account_cooldown_seconds // 2
            else:
                cooldown_seconds = cooldown_seconds or self.settings.account_cooldown_seconds

            account.state.status = new_status
            account.state.cooldown_until = datetime.now(timezone.utc) + timedelta(
                seconds=cooldown_seconds
            )

            logger.warning(
                "Account %d marked %s (HTTP %s, cooldown %ss): %s",
                account.index,
                new_status.value,
                status_code,
                cooldown_seconds,
                error_message,
            )

    def _classify_error(
        self,
        status_code: Optional[int],
        error_message: Optional[str],
    ) -> tuple[AccountStatus, Optional[float]]:
        """Classify an HTTP error into an account status."""
        msg = (error_message or "").lower()

        if status_code in (401, 403):
            return AccountStatus.AUTH_ERROR, None

        if status_code == 429:
            if any(k in msg for k in ("quota", "exhausted", "limit reached", "usage", "token")):
                return AccountStatus.TOKEN_EXHAUSTED, None
            return AccountStatus.RATE_LIMITED, None

        if status_code and status_code >= 500:
            return AccountStatus.TEMPORARILY_UNAVAILABLE, None

        if any(k in msg for k in ("connection", "timeout", "reset", "refused", "dns")):
            return AccountStatus.TEMPORARILY_UNAVAILABLE, None

        return AccountStatus.TEMPORARILY_UNAVAILABLE, None

    async def mark_healthy(self, account: Account) -> None:
        """Explicitly mark an account as healthy (used by health checks)."""
        async with account.lock:
            account.state.status = AccountStatus.HEALTHY
            account.state.cooldown_until = None
            account.state.last_error = None
            account.state.last_status_code = None
            account.state.consecutive_failures = 0
            account.state.last_checked = datetime.now(timezone.utc)

    async def mark_unhealthy(self, account: Account, reason: str) -> None:
        """Mark an account as temporarily unavailable from health check."""
        async with account.lock:
            account.state.status = AccountStatus.TEMPORARILY_UNAVAILABLE
            account.state.last_error = reason
            account.state.last_checked = datetime.now(timezone.utc)
            account.state.cooldown_until = datetime.now(timezone.utc) + timedelta(
                seconds=self.settings.account_cooldown_seconds
            )
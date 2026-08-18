"""Account pool management with health tracking and failover logic."""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from app.config import settings
from app.models import AccountState, AccountStatus
from app.utils import mask_key

if TYPE_CHECKING:
    from app.key_store import KeyRecord

logger = logging.getLogger(__name__)


class Account:
    """Represents a single Ollama Cloud API account."""

    def __init__(self, index: int, api_key: str, key_id: str = "", label: str = ""):
        self.index = index
        self.api_key = api_key
        self.key_id = key_id
        self.label = label or f"Account {index + 1}"
        self.status = AccountStatus(
            index=index,
            key_id=key_id or None,
            label=self.label,
            key_preview=mask_key(api_key),
            state=AccountState.UNKNOWN,
        )
        self._lock = asyncio.Lock()
        self._in_flight = 0

    def __repr__(self) -> str:
        return f"Account(index={self.index}, state={self.status.state.value})"

    @property
    def is_available(self) -> bool:
        """Check if the account is currently available for requests."""
        if self.status.state == AccountState.DISABLED:
            return False
        if self.status.cooldown_until and datetime.utcnow() < self.status.cooldown_until:
            return False
        if self.status.state in (
            AccountState.HEALTHY,
            AccountState.UNKNOWN,
        ):
            return True
        # For temporarily unavailable states, check if cooldown has expired
        if self.status.state in (
            AccountState.RATE_LIMITED,
            AccountState.TOKEN_EXHAUSTED,
            AccountState.TEMPORARILY_UNAVAILABLE,
            AccountState.AUTH_ERROR,
        ):
            if self.status.cooldown_until and datetime.utcnow() >= self.status.cooldown_until:
                return True
        return False

    async def mark_success(self):
        """Mark the account as having successfully handled a request."""
        async with self._lock:
            self.status.success_count += 1
            self.status.consecutive_failures = 0
            self.status.last_used = datetime.utcnow()
            if self.status.state != AccountState.HEALTHY:
                self.status.state = AccountState.HEALTHY
                self.status.cooldown_until = None
                self.status.last_error = None
                logger.info(f"Account {self.index} recovered to HEALTHY")

    async def mark_failure(
        self,
        error: str,
        state: AccountState = AccountState.TEMPORARILY_UNAVAILABLE,
        cooldown_seconds: Optional[float] = None,
    ):
        """Mark the account as having failed a request."""
        async with self._lock:
            self.status.failure_count += 1
            self.status.consecutive_failures += 1
            self.status.last_error = error
            self.status.last_used = datetime.utcnow()

            cooldown = cooldown_seconds or settings.account_cooldown_seconds

            # Exponential backoff for repeated failures
            if self.status.consecutive_failures > 1:
                cooldown *= min(2 ** (self.status.consecutive_failures - 1), 8)

            self.status.cooldown_until = datetime.utcnow() + timedelta(seconds=cooldown)
            self.status.state = state

            logger.warning(
                f"Account {self.index} marked {state.value}: {error}. "
                f"Cooldown until {self.status.cooldown_until.isoformat()}"
            )

    async def acquire(self) -> bool:
        """Try to acquire a slot for this account."""
        async with self._lock:
            if self._in_flight >= settings.max_concurrent_requests_per_account:
                return False
            self._in_flight += 1
            return True

    async def release(self):
        """Release a slot for this account."""
        async with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    async def record_usage(self, prompt_tokens: int, completion_tokens: int, total_tokens: int):
        """Accumulate token usage from a successful response's `usage` field."""
        async with self._lock:
            self.status.total_prompt_tokens += max(0, prompt_tokens)
            self.status.total_completion_tokens += max(0, completion_tokens)
            self.status.total_tokens += max(0, total_tokens)


class AccountPool:
    """Manages a pool of Ollama Cloud API accounts with failover logic."""

    def __init__(self, api_keys: List[str]):
        self.accounts: List[Account] = [
            Account(index=i, api_key=key) for i, key in enumerate(api_keys)
        ]
        self._init_common()

    def _init_common(self):
        self._round_robin_index = 0
        self._lock = asyncio.Lock()
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._start_time = time.time()

    @classmethod
    def from_records(cls, records: List["KeyRecord"]) -> "AccountPool":
        """Build a pool from dashboard-managed KeyRecords (keeps id/label)."""
        pool = cls.__new__(cls)
        pool.accounts = [
            Account(index=i, api_key=r.api_key, key_id=r.id, label=r.label)
            for i, r in enumerate(records)
        ]
        pool._init_common()
        return pool

    async def sync_from_records(self, records: List["KeyRecord"]) -> None:
        """Reconcile the live pool with an updated key list, in place.

        Existing accounts (matched by key_id) keep their stats/state; new
        keys get a fresh Account; removed keys are dropped. This lets the
        dashboard add/edit/remove keys without restarting the gateway or
        losing in-memory stats for keys that didn't change.
        """
        async with self._lock:
            existing_by_id = {a.key_id: a for a in self.accounts if a.key_id}
            new_accounts: List[Account] = []
            for i, rec in enumerate(records):
                existing = existing_by_id.get(rec.id)
                if existing is not None:
                    existing.api_key = rec.api_key
                    existing.label = rec.label
                    existing.index = i
                    existing.status.index = i
                    existing.status.label = rec.label
                    existing.status.key_preview = mask_key(rec.api_key)
                    new_accounts.append(existing)
                else:
                    new_accounts.append(
                        Account(index=i, api_key=rec.api_key, key_id=rec.id, label=rec.label)
                    )
            self.accounts = new_accounts
            self._round_robin_index = 0

    @property
    def total_accounts(self) -> int:
        return len(self.accounts)

    @property
    def healthy_accounts(self) -> int:
        return sum(1 for a in self.accounts if a.status.state == AccountState.HEALTHY)

    @property
    def available_accounts(self) -> int:
        return sum(1 for a in self.accounts if a.is_available)

    @property
    def total_requests(self) -> int:
        return self._total_requests

    @property
    def successful_requests(self) -> int:
        return self._successful_requests

    @property
    def failed_requests(self) -> int:
        return self._failed_requests

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    async def get_next_account(self, excluded_indices: Optional[List[int]] = None) -> Optional[Account]:
        """Get the next available account using round-robin selection."""
        excluded = set(excluded_indices or [])
        async with self._lock:
            for _ in range(len(self.accounts)):
                idx = self._round_robin_index % len(self.accounts)
                self._round_robin_index = (self._round_robin_index + 1) % len(self.accounts)

                if idx in excluded:
                    continue

                account = self.accounts[idx]
                if account.is_available and await account.acquire():
                    self._total_requests += 1
                    return account

        return None

    async def release_account(self, account: Account):
        """Release an account back to the pool."""
        await account.release()

    async def record_success(self, account: Account):
        """Record a successful request."""
        await account.mark_success()
        self._successful_requests += 1

    async def record_failure(
        self,
        account: Account,
        error: str,
        state: AccountState = AccountState.TEMPORARILY_UNAVAILABLE,
        cooldown_seconds: Optional[float] = None,
    ):
        """Record a failed request."""
        await account.mark_failure(error, state, cooldown_seconds)
        self._failed_requests += 1

    async def record_usage(self, account: Account, usage: Dict) -> None:
        """Record token usage from a successful response's `usage` field."""
        await account.record_usage(
            usage.get("prompt_tokens", 0) or 0,
            usage.get("completion_tokens", 0) or 0,
            usage.get("total_tokens", 0) or 0,
        )

    def get_all_statuses(self) -> List[AccountStatus]:
        """Get the status of all accounts."""
        return [acc.status for acc in self.accounts]

    def get_safe_statuses(self) -> List[Dict]:
        """Get safe (no API keys) status info for all accounts."""
        result = []
        for acc in self.accounts:
            status = acc.status.model_dump()
            status["available"] = acc.is_available
            status["in_flight"] = acc._in_flight
            result.append(status)
        return result

    async def update_account_state(self, index: int, state: AccountState, error: Optional[str] = None):
        """Update the state of a specific account (used by health checks)."""
        if 0 <= index < len(self.accounts):
            account = self.accounts[index]
            async with account._lock:
                account.status.state = state
                account.status.last_checked = datetime.utcnow()
                if error:
                    account.status.last_error = error
                if state == AccountState.HEALTHY:
                    account.status.consecutive_failures = 0
                    account.status.cooldown_until = None

    def get_account_by_index(self, index: int) -> Optional[Account]:
        """Get an account by its index."""
        if 0 <= index < len(self.accounts):
            return self.accounts[index]
        return None


# Global account pool instance
account_pool: Optional[AccountPool] = None


def initialize_pool(api_keys: List[str]) -> AccountPool:
    """Initialize the global account pool from a plain list of key strings."""
    global account_pool
    account_pool = AccountPool(api_keys)
    logger.info(f"Initialized account pool with {len(api_keys)} account(s)")
    return account_pool


def initialize_pool_from_records(records: List["KeyRecord"]) -> AccountPool:
    """Initialize the global account pool from dashboard-managed KeyRecords."""
    global account_pool
    account_pool = AccountPool.from_records(records)
    logger.info(f"Initialized account pool with {len(records)} account(s) from key store")
    return account_pool


def get_account_pool() -> Optional[AccountPool]:
    """Return the current global account pool.

    Always call this instead of importing `account_pool` by name — a plain
    `from app.account_manager import account_pool` binds to whatever the
    value was at import time (None, since this module hasn't initialized
    the pool yet) and will never see later reassignment.
    """
    return account_pool
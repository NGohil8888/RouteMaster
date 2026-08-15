import time
from fastapi import Request, HTTPException
from app.config import settings

class RateLimiter:
    def __init__(self):
        self.requests = {}

    async def check(self, key: str):
        if not settings.RATE_LIMIT_ENABLED:
            return True
        now = time.time()
        window = settings.RATE_LIMIT_WINDOW
        limit = settings.RATE_LIMIT_REQUESTS
        if key not in self.requests:
            self.requests[key] = []
        self.requests[key] = [t for t in self.requests[key] if now - t < window]
        if len(self.requests[key]) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        self.requests[key].append(now)
        return True

rate_limiter = RateLimiter()
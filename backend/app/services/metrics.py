import time
from typing import Dict, Any, List
from collections import defaultdict, deque
from datetime import datetime, timedelta

class MetricsCollector:
    def __init__(self):
        self.request_times: deque = deque(maxlen=10000)
        self.server_requests: Dict[int, int] = defaultdict(int)
        self.status_counts: Dict[str, int] = defaultdict(int)
        self.error_counts: Dict[int, int] = defaultdict(int)
        self._start_time = time.time()

    def record_request(self, server_id: int, response_time_ms: float, status: str):
        self.request_times.append((datetime.utcnow(), response_time_ms))
        self.server_requests[server_id] += 1
        self.status_counts[status] += 1
        if status in ('error', 'failed', 'timeout'):
            self.error_counts[server_id] += 1

    def get_stats(self, window_minutes: int = 5) -> Dict[str, Any]:
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        recent = [rt for dt, rt in self.request_times if dt > cutoff]
        total = len(recent)
        avg_latency = sum(recent) / max(len(recent), 1)
        rpm = total / max(window_minutes, 1)
        errors = sum(1 for dt, rt in self.request_times if dt > cutoff and rt < 0)
        error_rate = errors / max(total, 1)
        return {
            'total_requests': total,
            'requests_per_minute': round(rpm, 2),
            'avg_latency_ms': round(avg_latency, 2),
            'error_rate': round(error_rate, 4),
            'uptime_seconds': int(time.time() - self._start_time)
        }

    def get_server_metrics(self, server_id: int) -> Dict[str, Any]:
        return {
            'total_requests': self.server_requests.get(server_id, 0),
            'error_count': self.error_counts.get(server_id, 0)
        }

metrics = MetricsCollector()
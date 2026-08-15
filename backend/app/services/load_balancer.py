from typing import List, Optional
from app.models.server import OllamaServer

class LoadBalancer:
    @staticmethod
    def least_connections(servers: List[OllamaServer]) -> Optional[OllamaServer]:
        healthy = [s for s in servers if s.is_healthy and s.enabled]
        if not healthy:
            return None
        return min(healthy, key=lambda s: s.current_load)

    @staticmethod
    def weighted_round_robin(servers: List[OllamaServer], index: int) -> tuple[Optional[OllamaServer], int]:
        healthy = [s for s in servers if s.is_healthy and s.enabled]
        if not healthy:
            return None, index
        weighted = []
        for s in healthy:
            weighted.extend([s] * max(s.weight, 1))
        if not weighted:
            return None, index
        selected = weighted[index % len(weighted)]
        return selected, (index + 1) % len(weighted)
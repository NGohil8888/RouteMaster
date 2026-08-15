import asyncio
import logging
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import httpx

from app.models.server import OllamaServer
from app.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class RoutingMode(str, Enum):
    """Available routing modes."""
    AUTO = "auto"
    ROUND_ROBIN = "round_robin"
    LEAST_LOAD = "least_load"
    FASTEST_SERVER = "fastest_server"
    PRIORITY = "priority"
    MANUAL = "manual"
    FAILOVER_ONLY = "failover_only"


class HermesAgent:
    """Intelligent routing agent for Ollama requests."""
    
    def __init__(self):
        self.routing_mode = RoutingMode.AUTO
        self.clients: Dict[str, OllamaClient] = {}
    
    def set_routing_mode(self, mode: RoutingMode):
        """Set the routing mode."""
        self.routing_mode = mode
        logger.info(f"Routing mode changed to: {mode.value}")
    
    async def route_request(
        self,
        db: Session,
        model: str,
        request_data: Dict[str, Any],
        preferred_server_id: Optional[int] = None
    ) -> tuple[OllamaServer, OllamaClient]:
        """
        Route a request to the most appropriate Ollama server.
        
        Args:
            db: Database session
            model: Model name requested
            request_data: Full request data
            preferred_server_id: Optional preferred server ID
        
        Returns:
            Tuple of (OllamaServer, OllamaClient)
        
        Raises:
            ValueError: If no suitable server found
        """
        # Get all healthy servers that have the model
        available_servers = db.query(OllamaServer).filter(
            OllamaServer.is_enabled == True,
            OllamaServer.is_healthy == True,
            OllamaServer.available_models.contains(model)
        ).all()
        
        if not available_servers:
            raise ValueError(f"No available servers with model: {model}")
        
        # Route based on configured mode
        if self.routing_mode == RoutingMode.AUTO:
            selected = self._score_servers(available_servers)
        elif self.routing_mode == RoutingMode.ROUND_ROBIN:
            selected = self._round_robin_select(available_servers)
        elif self.routing_mode == RoutingMode.LEAST_LOAD:
            selected = self._least_load_select(available_servers)
        elif self.routing_mode == RoutingMode.FASTEST_SERVER:
            selected = self._fastest_select(available_servers)
        elif self.routing_mode == RoutingMode.PRIORITY:
            selected = self._priority_select(available_servers)
        elif self.routing_mode == RoutingMode.MANUAL:
            if preferred_server_id:
                selected = next(
                    (s for s in available_servers if s.id == preferred_server_id),
                    available_servers[0]
                )
            else:
                selected = available_servers[0]
        elif self.routing_mode == RoutingMode.FAILOVER_ONLY:
            selected = self._failover_select(available_servers)
        else:
            selected = available_servers[0]
        
        # Get or create client
        client = self._get_client(selected.base_url)
        
        return selected, client
    
    def _score_servers(self, servers: List[OllamaServer]) -> OllamaServer:
        """
        Score servers using weighted algorithm.
        
        Scoring formula:
        score = (load_factor × 0.35)
              + (latency_factor × 0.30)
              + (error_factor × 0.20)
              + (priority_factor × 0.10)
              + (weight_factor × 0.05)
        """
        scores = {}
        
        for server in servers:
            # Calculate factors (0-1 scale)
            load_factor = 1 - min(
                server.current_active_requests / max(server.max_concurrent_requests, 1),
                1.0
            )
            
            latency_factor = 1 / (1 + server.average_latency_ms / 1000)
            
            error_factor = 1 - min(server.error_rate, 1.0)
            
            priority_factor = server.priority / 10.0
            
            max_weight = max((s.weight for s in servers), 1)
            weight_factor = server.weight / max_weight
            
            # Weighted score
            score = (
                load_factor * 0.35 +
                latency_factor * 0.30 +
                error_factor * 0.20 +
                priority_factor * 0.10 +
                weight_factor * 0.05
            )
            
            scores[server.id] = score
        
        # Return server with highest score
        best_id = max(scores, key=scores.get)
        return next(s for s in servers if s.id == best_id)
    
    def _round_robin_select(self, servers: List[OllamaServer]) -> OllamaServer:
        """Round robin selection."""
        # Simple implementation: sort by ID and return first
        # In production, would use a counter
        return sorted(servers, key=lambda s: s.id)[0]
    
    def _least_load_select(self, servers: List[OllamaServer]) -> OllamaServer:
        """Select server with least active requests."""
        return min(servers, key=lambda s: s.current_active_requests)
    
    def _fastest_select(self, servers: List[OllamaServer]) -> OllamaServer:
        """Select server with lowest latency."""
        return min(servers, key=lambda s: s.average_latency_ms)
    
    def _priority_select(self, servers: List[OllamaServer]) -> OllamaServer:
        """Select highest priority server (lowest number)."""
        return min(servers, key=lambda s: s.priority)
    
    def _failover_select(self, servers: List[OllamaServer]) -> OllamaServer:
        """Select preferred server if available."""
        # Return first enabled server (would be primary)
        return servers[0]
    
    def _get_client(self, base_url: str) -> OllamaClient:
        """Get or create HTTP client for server."""
        if base_url not in self.clients:
            self.clients[base_url] = OllamaClient(base_url)
        return self.clients[base_url]
    
    async def close_clients(self):
        """Close all HTTP clients."""
        for client in self.clients.values():
            await client.close()
        self.clients.clear()

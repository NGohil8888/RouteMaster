import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from app.config import settings
from app.database import SessionLocal
from app.models.server import OllamaServer
from app.services.ollama_client import OllamaClient
import json

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Background service for monitoring Ollama server health."""
    
    def __init__(self):
        self.is_running = False
        self.task: asyncio.Task = None
        self.check_interval = settings.HEALTH_CHECK_INTERVAL_SECONDS
        self.timeout = settings.HEALTH_CHECK_TIMEOUT_SECONDS
        self.failure_threshold = settings.HEALTH_CHECK_FAILURES_THRESHOLD
    
    async def start(self):
        """Start the health monitoring loop."""
        if self.is_running:
            logger.warning("Health monitor already running")
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info("Health monitor started")
    
    async def stop(self):
        """Stop the health monitoring loop."""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Health monitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self.is_running:
            try:
                db = SessionLocal()
                await self._check_all_servers(db)
                db.close()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_all_servers(self, db: Session):
        """Check health of all registered servers."""
        servers = db.query(OllamaServer).all()
        
        for server in servers:
            if not server.is_enabled:
                continue
            
            await self._check_server_health(db, server)
    
    async def _check_server_health(self, db: Session, server: OllamaServer):
        """Check health of a single server."""
        client = OllamaClient(server.base_url, timeout=self.timeout)
        
        try:
            start_time = datetime.utcnow()
            response = await client.health_check()
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if response:
                # Successful check
                server.is_healthy = True
                server.consecutive_failures = 0
                server.last_health_check = datetime.utcnow()
                server.average_latency_ms = (
                    server.average_latency_ms * 0.7 + latency_ms * 0.3
                )
                
                # Update available models
                try:
                    tags_response = await client.get_tags()
                    models = [m.get("name", "") for m in tags_response.get("models", [])]
                    server.available_models = json.dumps(models)
                except Exception as e:
                    logger.warning(f"Failed to get models from {server.base_url}: {e}")
                
                logger.debug(f"Server {server.name} is healthy (latency: {latency_ms:.0f}ms)")
            else:
                # Failed check
                server.consecutive_failures += 1
                if server.consecutive_failures >= self.failure_threshold:
                    server.is_healthy = False
                    logger.warning(f"Server {server.name} marked as unhealthy")
                else:
                    logger.info(
                        f"Server {server.name} failed health check "
                        f"({server.consecutive_failures}/{self.failure_threshold})"
                    )
        
        except asyncio.TimeoutError:
            logger.warning(f"Health check timeout for {server.name}")
            server.consecutive_failures += 1
            if server.consecutive_failures >= self.failure_threshold:
                server.is_healthy = False
        
        except Exception as e:
            logger.error(f"Health check error for {server.name}: {e}")
            server.consecutive_failures += 1
            if server.consecutive_failures >= self.failure_threshold:
                server.is_healthy = False
        
        finally:
            await client.close()
            db.commit()


# Global health monitor instance
health_monitor = HealthMonitor()

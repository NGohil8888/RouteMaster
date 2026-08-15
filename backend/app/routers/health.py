from fastapi import APIRouter
from app.services.health_monitor import health_monitor
from app.services.hermes_agent import hermes

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health():
    return {
        "status": "healthy",
        "monitor_running": health_monitor.running,
        "routing_mode": hermes.get_routing_mode().value,
    }
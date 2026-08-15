from .auth import router as auth_router
from .servers import router as servers_router
from .models import router as models_router
from .chat import router as chat_router
from .dashboard import router as dashboard_router
from .logs import router as logs_router
from .health import router as health_router
from .test import router as test_router

__all__ = [
    "auth",
    "servers",
    "models",
    "chat",
    "dashboard",
    "logs",
    "health",
    "test",
]

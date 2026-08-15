from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.database import init_db
from app.services.health_monitor import health_monitor
from app.routers import auth, servers, models, chat, dashboard, logs, health, test

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await health_monitor.start()
    yield
    await health_monitor.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(servers.router, prefix=settings.API_PREFIX)
app.include_router(models.router, prefix=settings.API_PREFIX)
app.include_router(dashboard.router, prefix=settings.API_PREFIX)
app.include_router(logs.router, prefix=settings.API_PREFIX)
app.include_router(health.router, prefix=settings.API_PREFIX)
app.include_router(test.router, prefix=settings.API_PREFIX)

# OpenAI-compatible routes (mounted at /v1)
app.include_router(chat.router, prefix=settings.OPENAI_COMPATIBLE_PREFIX)
app.include_router(models.router, prefix=settings.OPENAI_COMPATIBLE_PREFIX)


@app.get("/health")
def root_health():
    return {"status": "ok", "version": settings.APP_VERSION}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG
    )
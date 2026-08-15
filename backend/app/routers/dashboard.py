from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.server import OllamaServer, RequestLog
from app.schemas.server import DashboardStats, SystemConfig
from app.services.hermes_agent import hermes, RoutingMode
from app.services.metrics import metrics
from app.middleware.auth import require_admin
from datetime import datetime, timedelta

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/stats", response_model=DashboardStats)
def get_stats(db: Session = Depends(get_db)):
    servers = db.query(OllamaServer).all()
    online = sum(1 for s in servers if s.is_healthy and s.enabled)
    total_models = db.query(ServerModel).filter(ServerModel.available == True).distinct(ServerModel.model_name).count()
    active = sum(s.current_load for s in servers)
    m = metrics.get_stats(window_minutes=5)
    return DashboardStats(
        total_servers=len(servers),
        online_servers=online,
        offline_servers=len(servers) - online,
        active_requests=active,
        requests_per_minute=m["requests_per_minute"],
        avg_latency_ms=m["avg_latency_ms"],
        error_rate=m["error_rate"],
        total_models=total_models
    )

@router.get("/chart-data")
def chart_data(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    points = []
    for i in range(30):
        t = now - timedelta(minutes=29-i)
        t_next = t + timedelta(minutes=1)
        count = db.query(RequestLog).filter(
            RequestLog.timestamp >= t,
            RequestLog.timestamp < t_next
        ).count()
        latency = db.query(func.avg(RequestLog.response_time_ms)).filter(
            RequestLog.timestamp >= t,
            RequestLog.timestamp < t_next,
            RequestLog.status == "success"
        ).scalar() or 0
        points.append({
            "time": t.strftime("%H:%M"),
            "requests": count,
            "latency": round(float(latency), 1)
        })
    return points

@router.get("/server-distribution")
def server_distribution(db: Session = Depends(get_db)):
    servers = db.query(OllamaServer).filter(OllamaServer.enabled == True).all()
    return [{
        "name": s.name,
        "load": s.current_load,
        "max": s.max_concurrent,
        "latency": s.response_latency_ms,
        "healthy": s.is_healthy
    } for s in servers]

@router.get("/routing-mode")
def get_routing_mode():
    return {"mode": hermes.get_routing_mode().value}

@router.post("/routing-mode")
def set_routing_mode(config: SystemConfig, admin=Depends(require_admin)):
    try:
        mode = RoutingMode(config.routing_mode.upper())
        hermes.set_routing_mode(mode)
        return {"mode": mode.value}
    except ValueError:
        return {"error": "Invalid routing mode"}
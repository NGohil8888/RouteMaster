from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from app.database import get_db
from app.models.server import RequestLog, OllamaServer
from app.schemas.server import LogEntry
from app.middleware.auth import require_admin

router = APIRouter(prefix="/logs", tags=["logs"])

@router.get("", response_model=List[LogEntry])
def list_logs(
    db: Session = Depends(get_db),
    server_id: Optional[int] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    request_id: Optional[str] = None,
    minutes: int = Query(60, ge=1, le=10080),
    limit: int = Query(100, ge=1, le=1000)
):
    q = db.query(RequestLog).join(OllamaServer, isouter=True)
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    q = q.filter(RequestLog.timestamp >= cutoff)
    if server_id:
        q = q.filter(RequestLog.server_id == server_id)
    if model:
        q = q.filter(RequestLog.model == model)
    if status:
        q = q.filter(RequestLog.status == status)
    if request_id:
        q = q.filter(RequestLog.request_id.ilike(f"%{request_id}%"))
    logs = q.order_by(RequestLog.timestamp.desc()).limit(limit).all()
    result = []
    for log in logs:
        entry = LogEntry.model_validate(log)
        entry.server_name = log.server.name if log.server else None
        result.append(entry)
    return result

@router.get("/summary")
def logs_summary(db: Session = Depends(get_db), minutes: int = 60):
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    total = db.query(RequestLog).filter(RequestLog.timestamp >= cutoff).count()
    success = db.query(RequestLog).filter(
        RequestLog.timestamp >= cutoff,
        RequestLog.status == "success"
    ).count()
    errors = total - success
    avg_latency = db.query(RequestLog).filter(
        RequestLog.timestamp >= cutoff,
        RequestLog.status == "success"
    ).with_entities(func.avg(RequestLog.response_time_ms)).scalar() or 0
    return {
        "total": total,
        "success": success,
        "errors": errors,
        "avg_latency_ms": round(float(avg_latency), 2)
    }
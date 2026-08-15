from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.server import OllamaServer, ServerModel
from app.schemas.server import ServerCreate, ServerUpdate, ServerResponse, ServerStatus, ServerModelInfo
from app.services.hermes_agent import hermes
from app.middleware.auth import require_admin
from app.utils.crypto import encrypt_value

router = APIRouter(prefix="/servers", tags=["servers"])

@router.get("", response_model=List[ServerResponse])
def list_servers(db: Session = Depends(get_db)):
    return db.query(OllamaServer).all()

@router.get("/status", response_model=List[ServerStatus])
def servers_status(db: Session = Depends(get_db)):
    result = []
    for s in db.query(OllamaServer).all():
        result.append(ServerStatus(
            id=s.id,
            name=s.name,
            url=s.url,
            is_healthy=s.is_healthy,
            current_load=s.current_load,
            response_latency_ms=s.response_latency_ms,
            error_rate=s.error_rate,
            enabled=s.enabled,
            models_count=len([m for m in s.models if m.available])
        ))
    return result

@router.post("", response_model=ServerResponse)
def create_server(server: ServerCreate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    db_server = OllamaServer(
        name=server.name,
        url=server.url,
        priority=server.priority,
        weight=server.weight,
        enabled=server.enabled,
        max_concurrent=server.max_concurrent,
        timeout_seconds=server.timeout_seconds,
        api_key_encrypted=encrypt_value(server.api_key) if server.api_key else None
    )
    db.add(db_server)
    db.commit()
    db.refresh(db_server)
    return db_server

@router.get("/{server_id}", response_model=ServerResponse)
def get_server(server_id: int, db: Session = Depends(get_db)):
    s = db.query(OllamaServer).filter(OllamaServer.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")
    return s

@router.put("/{server_id}", response_model=ServerResponse)
def update_server(server_id: int, update: ServerUpdate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    s = db.query(OllamaServer).filter(OllamaServer.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        if field == "api_key" and value:
            setattr(s, "api_key_encrypted", encrypt_value(value))
        else:
            setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return s

@router.delete("/{server_id}")
def delete_server(server_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    s = db.query(OllamaServer).filter(OllamaServer.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")
    db.delete(s)
    db.commit()
    return {"ok": True}

@router.post("/{server_id}/test")
async def test_server(server_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    s = db.query(OllamaServer).filter(OllamaServer.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")
    result = await hermes.test_server_connection(s)
    return result

@router.get("/{server_id}/models", response_model=List[ServerModelInfo])
def server_models(server_id: int, db: Session = Depends(get_db)):
    return db.query(ServerModel).filter(ServerModel.server_id == server_id).all()
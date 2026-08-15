from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.server import OllamaServer
from app.schemas.server import TestPromptRequest, TestPromptResponse, ClusterTestRequest, ClusterTestResult
from app.services.hermes_agent import hermes
from app.middleware.auth import require_admin

router = APIRouter(prefix="/test", tags=["test"])

@router.post("/prompt", response_model=TestPromptResponse)
async def test_prompt(req: TestPromptRequest, db: Session = Depends(get_db), admin=Depends(require_admin)):
    if req.server_id:
        server = db.query(OllamaServer).filter(OllamaServer.id == req.server_id).first()
    else:
        server, _, _ = await hermes.select_server(db, req.model)
    if not server:
        raise HTTPException(status_code=404, detail="No server available")
    result = await hermes.test_server_model(server, req.model, req.prompt, req.stream)
    if not result["success"]:
        raise HTTPException(status_code=502, detail=result.get("error"))
    return TestPromptResponse(
        response=result["response"],
        response_time_ms=result["response_time_ms"],
        tokens_used=len(result["response"].split()),
        server_name=result["server_name"],
        model=req.model,
        streaming=req.stream
    )

@router.post("/cluster", response_model=List[ClusterTestResult])
async def cluster_test(req: ClusterTestRequest, db: Session = Depends(get_db), admin=Depends(require_admin)):
    servers = db.query(OllamaServer).filter(
        OllamaServer.enabled == True,
        OllamaServer.is_healthy == True
    ).all()
    results = []
    for s in servers:
        has_model = any(m.model_name == req.model and m.available for m in s.models)
        if not has_model:
            continue
        result = await hermes.test_server_model(s, req.model, req.prompt, req.stream)
        results.append(ClusterTestResult(
            server_id=s.id,
            server_name=s.name,
            model=req.model,
            response=result.get("response", ""),
            response_time_ms=result["response_time_ms"],
            tokens_used=len(result.get("response", "").split()),
            status="success" if result["success"] else "error",
            error=result.get("error")
        ))
    return results
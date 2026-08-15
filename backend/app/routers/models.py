from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
import time
from app.database import get_db
from app.models.server import ServerModel, OllamaServer
from app.schemas.server import ServerModelInfo, ModelInfo, ModelsListResponse

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelsListResponse)
def list_models(db: Session = Depends(get_db)):
    models = (
        db.query(ServerModel)
        .filter(ServerModel.available == True)
        .distinct(ServerModel.model_name)
        .all()
    )
    seen = set()
    data = []
    for m in models:
        if m.model_name not in seen:
            seen.add(m.model_name)
            data.append(
                ModelInfo(
                    id=m.model_name,
                    object="model",
                    created=int(time.time()),
                    owned_by=m.family or "unknown",
                )
            )
    return ModelsListResponse(object="list", data=data)


@router.get("/cluster")
def cluster_models(db: Session = Depends(get_db)):
    servers = db.query(OllamaServer).filter(OllamaServer.enabled == True).all()
    result = []
    for s in servers:
        for m in s.models:
            if m.available:
                result.append(
                    {
                        "server_id": s.id,
                        "server_name": s.name,
                        "server_healthy": s.is_healthy,
                        "model_name": m.model_name,
                        "parameter_size": m.parameter_size,
                        "quantization": m.quantization,
                    }
                )
    return result
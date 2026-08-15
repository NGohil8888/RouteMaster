from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import json
import time
import uuid
from typing import Optional
from app.database import get_db
from app.models.server import OllamaServer, RequestLog
from app.schemas.server import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
)
from app.services.hermes_agent import hermes, RoutingMode
from app.services.metrics import metrics
from app.middleware.rate_limit import rate_limiter

router = APIRouter(prefix="/chat", tags=["chat"])


async def stream_chat_response(client, payload, server, log, start_time):
    completion_text = ""
    prompt_tokens = 0
    completion_tokens = 0
    try:
        async for line in client.chat_completion(**payload):
            if line.strip():
                try:
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        chunk = data["message"]["content"]
                        completion_text += chunk
                        completion_tokens += 1
                    if data.get("done"):
                        prompt_tokens = data.get("prompt_eval_count", 0)
                        completion_tokens = data.get("eval_count", 0)
                    event = {
                        "id": log.request_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": payload["model"],
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "content": data.get("message", {}).get("content", "")
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                    if data.get("done"):
                        event["choices"][0]["finish_reason"] = "stop"
                        event["choices"][0]["delta"] = {}
                        yield f"data: {json.dumps(event)}\n\n"
                except json.JSONDecodeError:
                    continue
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    finally:
        elapsed = (time.time() - start_time) * 1000
        log.response_time_ms = elapsed
        log.status = "success" if completion_text else "error"
        log.completion_tokens = completion_tokens
        log.prompt_tokens = prompt_tokens
        log.total_tokens = prompt_tokens + completion_tokens
        server.current_load = max(0, server.current_load - 1)
        metrics.record_request(server.id, elapsed, log.status)


@router.post("/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    request: Request,
    db: Session = Depends(get_db),
    x_routing_mode: Optional[str] = None,
    x_preferred_server: Optional[int] = None,
):
    client_ip = request.client.host if request.client else None
    await rate_limiter.check(f"ip:{client_ip}")

    mode = None
    if x_routing_mode:
        try:
            mode = RoutingMode(x_routing_mode.upper())
        except ValueError:
            pass

    server, client, used_mode = await hermes.route_request(
        db, req.model, mode=mode, preferred_server_id=x_preferred_server
    )
    if not server or not client:
        raise HTTPException(
            status_code=503, detail="No available Ollama servers for this model"
        )

    server.current_load += 1
    log = RequestLog(
        request_id=str(uuid.uuid4()),
        model=req.model,
        server_id=server.id,
        routing_mode=used_mode.value if used_mode else "AUTO",
        streaming=req.stream,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(log)
    db.commit()

    payload = {
        "model": req.model,
        "messages": req.messages,
        "stream": req.stream,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "top_p": req.top_p,
        "stop": req.stop,
        "extra_body": req.extra_body,
    }

    start = time.time()

    if req.stream:
        return StreamingResponse(
            stream_chat_response(client, payload, server, log, start),
            media_type="text/event-stream",
        )

    try:
        response_text = ""
        prompt_tokens = 0
        completion_tokens = 0
        async for line in client.chat_completion(**payload):
            if line.strip():
                try:
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        response_text += data["message"]["content"]
                    if data.get("done"):
                        prompt_tokens = data.get("prompt_eval_count", 0)
                        completion_tokens = data.get("eval_count", 0)
                except json.JSONDecodeError:
                    continue

        elapsed = (time.time() - start) * 1000
        log.response_time_ms = elapsed
        log.status = "success"
        log.prompt_tokens = prompt_tokens
        log.completion_tokens = completion_tokens
        log.total_tokens = prompt_tokens + completion_tokens
        server.current_load = max(0, server.current_load - 1)
        metrics.record_request(server.id, elapsed, "success")
        db.commit()

        return ChatCompletionResponse(
            id=log.request_id,
            created=int(time.time()),
            model=req.model,
            choices=[
                ChatCompletionChoice(
                    message={"role": "assistant", "content": response_text},
                    finish_reason="stop",
                )
            ],
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        )
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        log.response_time_ms = elapsed
        log.status = "error"
        log.error_message = str(e)
        server.current_load = max(0, server.current_load - 1)
        metrics.record_request(server.id, elapsed, "error")
        db.commit()
        raise HTTPException(status_code=502, detail=str(e))
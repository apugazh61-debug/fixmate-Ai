"""
FastAPI entrypoint for FixMate AI GitHub CI Webhook & VS Code Extension.

Endpoints:
- POST /webhook/github: Autonomous GitHub Actions failure webhook trigger.
- POST /analyze/inline: Sub-second offline diagnostic endpoint for VS Code.
- GET  /health: Health check.

Run with:
    uvicorn webhook_app:app --port 8000
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel

from core.engine import run_local_pipeline
from core import webhook_listener

app = FastAPI(
    title="FixMate AI CI & IDE Service",
    description="Autonomous CI webhook listener and IDE real-time analysis backend.",
    version="1.0.0",
)


class InlineAnalyzeRequest(BaseModel):
    code: str
    file_path: str = ""


@app.get("/")
@app.get("/health")
def health_check() -> dict[str, Any]:
    return {"status": "ok", "service": "FixMate AI Service", "offline_ready": True}


@app.post("/analyze/inline")
def analyze_inline(req: InlineAnalyzeRequest) -> dict[str, Any]:
    """Lightweight, sub-second local analysis endpoint used by the VS Code extension."""
    result = run_local_pipeline(req.code)
    return {
        "verified": result.verified,
        "fixed_code": result.fixed_code,
        "explanation": result.explanation,
        "attempts": result.attempts,
        "source": result.source,
        "issues": [
            {
                "error_type": i.error_type.value,
                "line": i.line,
                "message": i.message,
                "detail": i.detail,
                "confidence": i.confidence,
            }
            for i in result.issues
        ],
        "trace": [
            {
                "name": s.name,
                "status": s.status,
                "detail": s.detail,
            }
            for s in result.trace
        ],
    }


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
) -> dict[str, Any]:
    """Handle incoming GitHub webhook events with HMAC SHA-256 verification."""
    payload_bytes = await request.body()
    webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

    # Signature verification (mandatory when secret is set)
    if webhook_secret:
        if not webhook_listener.verify_signature(payload_bytes, x_hub_signature_256, webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-Hub-Signature-256 signature.",
            )
    elif not x_hub_signature_256:
        # Secret not configured on server and no signature provided
        pass

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed JSON payload: {exc}",
        ) from exc

    github_token = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", ""))

    if x_github_event == "workflow_run":
        return webhook_listener.handle_workflow_run_event(payload, github_token=github_token)

    return {
        "status": "ignored",
        "event": x_github_event,
        "message": f"Event '{x_github_event}' is not handled by FixMate CI listener.",
    }

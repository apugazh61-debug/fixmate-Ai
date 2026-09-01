"""
FastAPI entrypoint for FixMate AI GitHub CI Webhook.

Run with:
    uvicorn webhook_app:app --port 8000
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response, status

from core import webhook_listener

app = FastAPI(
    title="FixMate AI CI Webhook Service",
    description="Autonomous CI webhook listener for automated Python bug repairs.",
    version="1.0.0",
)


@app.get("/")
@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "FixMate AI Webhook Listener"}


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

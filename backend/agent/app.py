"""VESPER Cognitive Agent Swarm Microservice (Port 8001).

Exposes the Alfred supervisor and dynamic specialist swarm over HTTP/REST.
Receives user commands from `vesper-gateway` and returns structured
speech text, HUD cards, and execution metadata.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.agent.alfred import AlfredResponse, AlfredSupervisor
from backend.agent.registry import registry
from backend.shared.config import AGENT_PORT, ENVIRONMENT, LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("vesper.agent.service")

app = FastAPI(
    title="VESPER Agent Swarm Service",
    description="Cognitive Multi-Agent Swarm and Supervisor for VESPER",
    version="0.1.0",
)

# Global supervisor instance
supervisor = AlfredSupervisor(registry=registry)


class QueryRequest(BaseModel):
    """Input payload for a user query."""

    query: str
    session_id: Optional[str] = None
    client_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Service health and registered specialist discovery."""
    return {
        "status": "healthy",
        "service": "vesper-agent",
        "environment": ENVIRONMENT,
        "specialists": [s.name for s in registry.list_specialists()],
    }


@app.get("/specialists")
async def list_specialists() -> Dict[str, Any]:
    """Lists all registered specialist agents and their capabilities."""
    return {
        "specialists": [
            {
                "name": s.name,
                "description": s.description,
                "capabilities": s.get_capabilities(),
                "tools": s.get_tool_schemas(),
            }
            for s in registry.list_specialists()
        ]
    }


@app.post("/query", response_model=AlfredResponse)
async def handle_query(req: QueryRequest) -> AlfredResponse:
    """Processes a user command through the Alfred swarm supervisor."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        response = await supervisor.process_query(
            query=req.query,
            session_id=req.session_id,
            context=req.context,
        )
        return response
    except Exception as e:
        logger.exception(f"[AgentService] Error processing query: {e}")
        raise HTTPException(status_code=500, detail=f"Agent processing error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)

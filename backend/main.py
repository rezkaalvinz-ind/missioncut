"""MissionCut offline analysis API."""

import os
from collections import deque

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import Field

from .auth import AuthPayload, AuthResponse, UserResponse, current_user, ensure_schema, login, register
from .demo import demo_results
from .engine import compare, evaluate, find_paths, summary
from .models import CompareRequest, EvaluateRequest, GraphDocument, StrictModel
from .parsing import parse_graph


class BodySizeLimitMiddleware:
    """Bound complete request bodies, including requests without Content-Length."""

    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope.get("headers", [])).get(b"content-length")
        if length:
            try:
                if int(length) > self.max_bytes:
                    await self._too_large(send)
                    return
            except ValueError:
                pass
        messages = deque()
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    await self._too_large(send)
                    return
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                break

        async def replay():
            return messages.popleft() if messages else {"type": "http.disconnect"}

        await self.app(scope, replay, send)

    @staticmethod
    async def _too_large(send):
        body = b'{"error":{"code":"input_too_large","message":"Request exceeds 1 MB"}}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})


app = FastAPI(
    title="MissionCut API",
    version="0.1.0",
    description="Offline containment decision-support simulator. Does not change production networks.",
)
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "MISSIONCUT_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3010,http://127.0.0.1:3010",
    ).split(",")
    if origin.strip()
]
app.add_middleware(BodySizeLimitMiddleware, max_bytes=1_000_000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.on_event("startup")
def initialize_auth_database():
    try:
        ensure_schema()
    except Exception as exc:  # pragma: no cover - startup remains available for offline graph analysis
        app.state.auth_database_error = str(exc)


class GraphPathRequest(StrictModel):
    graph: GraphDocument
    source: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=80)
    max_paths: int = Field(default=50, ge=1, le=500)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": [{"location": list(e["loc"]), "message": e["msg"]} for e in exc.errors()],
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail)}}
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": {"code": "invalid_input", "message": str(exc)}})


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mode": "offline-simulation",
        "auth_database": "ready" if not getattr(app.state, "auth_database_error", None) else "unavailable",
    }


@app.post("/api/auth/register", response_model=AuthResponse, status_code=201)
def auth_register(payload: AuthPayload):
    return register(payload)


@app.post("/api/auth/login", response_model=AuthResponse)
def auth_login(payload: AuthPayload):
    return login(payload)


@app.get("/api/auth/me", response_model=UserResponse)
def auth_me(authorization: str | None = Header(default=None)):
    return current_user(authorization)


@app.get("/api/demo")
def demo():
    return demo_results()


@app.post("/api/graphs/validate")
def validate_graph(graph: GraphDocument):
    return {"valid": True, "summary": summary(graph), "graph": graph}


@app.post("/api/graphs/load")
async def load_graph(request: Request, format: str = "json"):
    raw = await request.body()
    graph = parse_graph(raw, format)
    return {"valid": True, "summary": summary(graph), "graph": graph}


@app.post("/api/graphs/summary")
def graph_summary(graph: GraphDocument):
    return summary(graph)


@app.post("/api/paths")
def paths(body: "GraphPathRequest"):
    return find_paths(body.graph, body.source, body.target, body.max_paths)


@app.post("/api/scenarios/evaluate")
def evaluate_scenario(body: EvaluateRequest):
    return evaluate(body.graph, body.scenario, body.sources, body.critical_targets)


@app.post("/api/scenarios/compare")
def compare_scenarios(body: CompareRequest):
    return compare(body.graph, body.scenarios, body.sources, body.critical_targets)


@app.post("/api/reports")
def report(body: CompareRequest):
    result = compare(body.graph, body.scenarios, body.sources, body.critical_targets)
    return {
        "title": "MissionCut containment comparison",
        "mode": "offline-simulation",
        "graph_summary": summary(body.graph),
        **result,
        "disclaimer": (
            "Based only on supplied topology and rules. This is not a real-world incident prediction "
            "or a production containment command."
        ),
    }

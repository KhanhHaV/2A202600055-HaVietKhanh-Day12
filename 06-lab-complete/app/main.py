"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting (Stateless with Redis)
  ✅ Cost guard (Stateless with Redis)
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
"""
import os
import time
import signal
import logging
import json
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import redis

from app.config import settings

# Mock LLM (thay bằng OpenAI/Anthropic khi có API key)
from utils.mock_llm import ask as llm_ask

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_in_flight_requests = 0

# ─────────────────────────────────────────────────────────
# Storage — Redis (Stateless)
# ─────────────────────────────────────────────────────────
try:
    if settings.redis_url:
        r = redis.from_url(settings.redis_url, decode_responses=True)
        r.ping()
        USE_REDIS = True
        logger.info("✅ Connected to Redis")
    else:
        USE_REDIS = False
        _memory_store = {}
        logger.warning("⚠️ Redis URL not set — using in-memory store (not scalable!)")
except Exception as e:
    USE_REDIS = False
    _memory_store = {}
    logger.error(f"❌ Failed to connect to Redis: {e}. Falling back to in-memory.")

# ─────────────────────────────────────────────────────────
# Rate Limiter (Redis-based Sliding Window)
# ─────────────────────────────────────────────────────────
def check_rate_limit(user_key: str):
    now = time.time()
    key = f"rl:{user_key}"
    limit = settings.rate_limit_per_minute
    
    if USE_REDIS:
        # Sliding window counter pattern with Redis sorted sets
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, now - 60)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, 60)
        _, _, count, _ = pipe.execute()
    else:
        # Fallback to simple in-memory window
        if key not in _memory_store:
            _memory_store[key] = []
        window = _memory_store[key]
        _memory_store[key] = [t for t in window if t > now - 60]
        _memory_store[key].append(now)
        count = len(_memory_store[key])

    if count > limit:
        logger.warning(f"Rate limit exceeded for {user_key}")
        raise HTTPException(
            status_code=429,
            detail={"error": "Rate limit exceeded", "limit": limit, "retry_after": "60s"}
        )

# ─────────────────────────────────────────────────────────
# Cost Guard (Redis-based)
# ─────────────────────────────────────────────────────────
def check_and_record_cost(user_id: str, input_tokens: int, output_tokens: int):
    today = time.strftime("%Y-%m-%d")
    cost_key = f"cost:{user_id}:{today}"
    
    # Simple pricing
    cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006
    
    if USE_REDIS:
        current_cost = float(r.get(cost_key) or 0)
        if current_cost + cost > settings.daily_budget_usd:
            raise HTTPException(402, "Daily budget exceeded. Please recharge or wait until tomorrow.")
        r.incrbyfloat(cost_key, cost)
        r.expire(cost_key, 86400 * 2) # Expire after 2 days
    else:
        current_cost = _memory_store.get(cost_key, 0.0)
        if current_cost + cost > settings.daily_budget_usd:
            raise HTTPException(402, "Daily budget exceeded")
        _memory_store[cost_key] = current_cost + cost
    
    return current_cost + cost

# ─────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        logger.warning(f"Invalid API Key attempt: {api_key}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
        )
    return "authorized_user" # In real app, map key to user_id

# ─────────────────────────────────────────────────────────
# Lifespan & Middlewares
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "env": settings.environment,
        "storage": "redis" if USE_REDIS else "in-memory"
    }))
    _is_ready = True
    yield
    _is_ready = False
    logger.info("Shutting down... finishing in-flight requests.")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.middleware("http")
async def process_request(request: Request, call_next):
    global _in_flight_requests
    start = time.time()
    _in_flight_requests += 1
    try:
        response: Response = await call_next(request)
        duration = round((time.time() - start) * 1000, 1)
        
        # Security Header best practices
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        logger.info(json.dumps({
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
            "ip": request.client.host if request.client else "unknown"
        }))
        return response
    finally:
        _in_flight_requests -= 1

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: str | None = None

class ChatResponse(BaseModel):
    answer: str
    session_id: str
    cost_status: dict

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/health", tags=["Ops"])
def health():
    uptime = round(time.time() - START_TIME, 1)
    return {
        "status": "ok",
        "uptime": uptime,
        "storage": "redis" if USE_REDIS else "in-memory",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/ready", tags=["Ops"])
def ready():
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    if USE_REDIS:
        try:
            r.ping()
        except:
            raise HTTPException(503, "Database connection lost")
    return {"status": "ready"}

@app.post("/ask", response_model=ChatResponse, tags=["Agent"])
async def ask_agent(
    body: ChatRequest,
    _auth: str = Depends(verify_api_key)
):
    # 1. Rate Limit
    check_rate_limit(_auth)
    
    # 2. Session Management (Stateless)
    session_id = body.session_id or str(uuid.uuid4())
    
    # 3. Simulate Agent Talk
    # In production, you would fetch history from Redis here
    # to provide context to the LLM.
    answer = llm_ask(body.question)
    
    # 4. Budget Tracking
    tokens_in = len(body.question.split()) * 2
    tokens_out = len(answer.split()) * 2
    total_cost = check_and_record_cost(_auth, tokens_in, tokens_out)
    
    return ChatResponse(
        answer=answer,
        session_id=session_id,
        cost_status={
            "today_cost_usd": round(total_cost, 5),
            "budget_usd": settings.daily_budget_usd,
            "percent_used": round((total_cost/settings.daily_budget_usd)*100, 1)
        }
    )

# ─────────────────────────────────────────────────────────
# Server Start
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=settings.timeout_graceful_shutdown if hasattr(settings, 'timeout_graceful_shutdown') else 30
    )

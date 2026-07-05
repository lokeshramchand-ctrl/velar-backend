from contextlib import asynccontextmanager
import logging
import httpx
from fastapi import FastAPI, Depends, Request

# Settings
from core.config import settings

# Middleware & Security
from prometheus_fastapi_instrumentator import Instrumentator
from core.security import validate_api_key
from core.rate_limiter import setup_rate_limiting, limiter

# Databases
from database.mongo import db
from database.milvus import vector_db

# Routers
from routers import v1, memory, analytics, rag
from routers.observability import router as observability_router


# Logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing application lifespan...")

    # MongoDB
    await db.connect(uri=settings.MONGODB_URI, db_name=settings.MONGODB_DB_NAME)

    # Milvus
    vector_db.connect(uri=settings.MILVUS_URI)

    yield

    logger.info("Tearing down application lifespan...")
    await db.disconnect()
    vector_db.disconnect()


# FastAPI App
app = FastAPI(
    title="Velar Transaction Intelligence API",
    description="Core engine for raw transaction ingestion and ML routing.",
    version="1.0.0",
    lifespan=lifespan
)

# Rate Limiting
setup_rate_limiting(app)

# Prometheus Metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# Routers (secured)
app.include_router(v1.router, dependencies=[Depends(validate_api_key)])
app.include_router(memory.router, dependencies=[Depends(validate_api_key)])
app.include_router(analytics.router, dependencies=[Depends(validate_api_key)])
app.include_router(rag.router, dependencies=[Depends(validate_api_key)])
app.include_router(observability_router, dependencies=[Depends(validate_api_key)])


# Public API
@app.post("/v1/categorize", dependencies=[Depends(validate_api_key)], tags=["Public API"])
@limiter.limit("50/minute")
async def public_categorize(request: Request, payload: dict):
    return {"status": "success", "message": "Transaction routed to Intelligence Engine."}


# Health Check
@app.get("/health", tags=["System"])
async def health_check():
    details = {}

    # MongoDB
    try:
        if db.client:
            await db.client.admin.command("ping")
            mongo_status = "connected"
            details["mongodb"] = "Active ping successful."
        else:
            mongo_status = "disconnected"
            details["mongodb"] = "Client not initialized."
    except Exception as e:
        mongo_status = "error"
        details["mongodb"] = str(e)

    # Milvus
    try:
        if vector_db.client:
            milvus_status = "connected"
            details["milvus"] = "Client initialized."
        else:
            milvus_status = "disconnected"
            details["milvus"] = "Client not initialized."
    except Exception as e:
        milvus_status = "error"
        details["milvus"] = str(e)

    # Ollama
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(settings.OLLAMA_URI)
            if resp.status_code == 200:
                ollama_status = "connected"
                details["ollama"] = "Ollama engine responding."
            else:
                ollama_status = "degraded"
                details["ollama"] = f"Status code: {resp.status_code}"
    except Exception as e:
        ollama_status = "error"
        details["ollama"] = str(e)

    overall_status = (
        "healthy"
        if mongo_status == "connected"
        and milvus_status == "connected"
        and ollama_status == "connected"
        else "degraded"
    )

    return {
        "status": overall_status,
        "services": {
            "mongodb": mongo_status,
            "milvus": milvus_status,
            "ollama": ollama_status,
        },
        "details": details,
    }


# Local Dev Entry Point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

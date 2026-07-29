import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database.mongo import db
from models.schemas import BehaviorPattern
from behaviour.behavior_engine import behavior_engine
from memory.decay_engine import decay_engine
from graphs.graph_builder import graph_engine
from embeddings.vectorizer import vectorizer
from embeddings.generate_embeddings import embedding_generator
from milvus.insert_vectors import vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/pipelines", tags=["Batch Pipelines"])


class MerchantRequest(BaseModel):
    merchant_name: str


@router.post("/behavior/run")
async def run_behavior_profiling(request: MerchantRequest):
    """Profiles a single merchant's behavioral signature (Phase 6). Writes to `behavior_patterns`."""
    try:
        return await behavior_engine.profile_merchant_behavior(request.merchant_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/behavior/run-all")
async def run_behavior_profiling_all():
    """
    Profiles every distinct merchant seen in `transactions`. This is the batch entry
    point that keeps `behavior_patterns` populated for /v1/analytics/subscriptions
    and /v1/analytics/anomaly/check, since nothing else calls the behavior engine.
    """
    merchant_names = await db.transactions.distinct("merchant")
    profiled, failed = [], []
    for name in merchant_names:
        if not name or name == "Unknown":
            continue
        try:
            await behavior_engine.profile_merchant_behavior(name)
            profiled.append(name)
        except Exception as e:
            logger.warning(f"Behavior profiling failed for '{name}': {e}")
            failed.append(name)
    return {"profiled": profiled, "failed": failed}


@router.post("/embeddings/sync")
async def sync_embeddings():
    """
    Generates and stores Milvus embeddings for every persisted behavior pattern
    (Phase 7). This is the missing link between `behavior_patterns` and the
    vector search used by /v1/explain and the clustering pipeline.
    """
    if vector_store.client is None:
        raise HTTPException(status_code=503, detail="Milvus is not connected.")

    docs = [doc async for doc in db.behavior_patterns.find()]
    synced, failed = [], []
    for doc in docs:
        merchant_name = doc.get("merchant_name", "Unknown")
        try:
            doc["_id"] = str(doc["_id"])
            pattern = BehaviorPattern(**doc)
            text = vectorizer.stringify_behavior(pattern)
            vector = await embedding_generator.generate(text)
            vector_store.insert_behavior_vector(
                pattern_id=pattern.id,
                merchant_name=pattern.merchant_name,
                vector=vector,
            )
            synced.append(merchant_name)
        except Exception as e:
            logger.warning(f"Embedding sync failed for '{merchant_name}': {e}")
            failed.append(merchant_name)
    return {"synced": synced, "failed": failed}


@router.post("/decay/sweep")
async def run_decay_sweep():
    """Archives merchant profiles inactive for 180+ days (Phase 4)."""
    archived_count = await decay_engine.run_archive_sweep()
    return {"archived_count": archived_count}


@router.post("/graph/build")
async def build_knowledge_graph():
    """Rebuilds the in-memory merchant knowledge graph from MongoDB (Phase 13)."""
    return await graph_engine.build_graph()


@router.get("/graph/neighborhood/{merchant_name}")
async def get_graph_neighborhood(merchant_name: str, radius: int = 2):
    """Returns the local ego-graph around a merchant. Call /graph/build first in this process."""
    return graph_engine.get_merchant_neighborhood(merchant_name, radius=radius)


@router.post("/clustering/run")
async def run_clustering():
    """
    Runs the UMAP + HDBSCAN discovery pipeline over stored Milvus vectors (Phase 8).
    Imported lazily so a missing/broken scikit-learn or umap-learn install only
    breaks this one endpoint instead of preventing the whole app from starting.
    """
    from clustering.cluster_engine import cluster_engine
    return await cluster_engine.run_discovery_pipeline()

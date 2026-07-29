from datetime import datetime, timezone
import re
from fastapi import APIRouter, Request
from pydantic import BaseModel
from models.schemas import CategorizeRequest, CategorizeResponse , ResolutionResult
from engines.rule_engine import rule_engine
from engines.confidence_engine import confidence_engine
from models.schemas import ConfidenceEvaluation
import time
from services.merchant_resolver import merchant_resolver
from database.mongo import db
from core.rate_limiter import limiter

router = APIRouter(prefix="/v1", tags=["Transaction Intelligence"])

@router.post("/categorize", response_model=CategorizeResponse)
@limiter.limit("50/minute")
async def categorize_transaction(request: Request, payload: CategorizeRequest):
    # Phase 11 Foresight: We can track latency here later
    start_time = time.time()

    # Process text through the Rule Engine
    result = rule_engine.categorize(payload.text)

    process_time = time.time() - start_time
    # TODO: Log process_time to Prometheus for Latency metrics
    amount = 0.0
    text_content = payload.text
    amount_match = re.search(r'₹\s*([0-9.,]+)', text_content)
    if amount_match:
        amount = float(amount_match.group(1).replace(',', ''))

    # 2. Save the fully enriched transaction to MongoDB
    insert_result = await db.transactions.insert_one({
        "user_id": "user_123", # Hardcoded for now so it perfectly matches your Analytics mock user
        "raw_text": text_content,
        "merchant": result["merchant"],
        "category": result["category"],
        "amount": amount,
        "confidence": result["confidence"],
        "timestamp": datetime.now(timezone.utc)
    })

    return {**result, "transaction_id": str(insert_result.inserted_id)}

class ResolveRequest(BaseModel):
    text: str

@router.post("/resolve", response_model=ResolutionResult)
async def resolve_transaction_merchant(request: ResolveRequest):
    """
    Phase 3 Endpoint: Takes a raw UPI/Bank transaction string and resolves it to a canonical merchant.
    """
    result = await merchant_resolver.resolve(request.text)
    return result

class MockModelPrediction(BaseModel):
    predicted_category: str
    raw_confidence: float

@router.post("/confidence/evaluate", response_model=ConfidenceEvaluation)
async def evaluate_prediction_confidence(request: MockModelPrediction):
    """
    Phase 5 Endpoint: Evaluates an upstream category prediction. 
    Forces the response to 'Unknown' if the confidence wall is breached.
    """
    evaluation = confidence_engine.evaluate(
        predicted_category=request.predicted_category,
        raw_confidence=request.raw_confidence
    )
    return evaluation
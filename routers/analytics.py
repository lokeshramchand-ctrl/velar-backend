from fastapi import APIRouter, Query
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone

from analytics.spending_patterns import spending_patterns
from analytics.subscriptions import subscription_engine
from analytics.trends import trend_analyzer
from analytics.anomaly_detection import anomaly_detector

router = APIRouter(prefix="/v1/analytics", tags=["Analytics Engine"])

# Mock User ID for Phase 13 testing
TEST_USER = "user_123"

@router.get("/patterns/categories")
async def get_category_patterns(days: int = Query(30, description="Lookback window in days")):
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    return await spending_patterns.get_category_breakdown(TEST_USER, start_date, end_date)

@router.get("/patterns/merchants")
async def get_top_merchants(limit: int = 5):
    return await spending_patterns.get_merchant_frequency(TEST_USER, limit)

@router.get("/subscriptions")
async def get_subscriptions():
    subs = await subscription_engine.identify_active_subscriptions(TEST_USER)
    total_burn = sum(sub["estimated_monthly_cost"] for sub in subs)
    return {
        "active_subscriptions": len(subs),
        "total_monthly_burn": total_burn,
        "details": subs
    }

@router.get("/trends/mom")
async def get_mom_trends():
    now = datetime.now(timezone.utc)
    return await trend_analyzer.calculate_mom_growth(TEST_USER, now.month, now.year)

@router.post("/anomaly/check")
async def check_anomaly(merchant: str, amount: float):
    """Real-time evaluation for the transaction ingestion pipeline."""
    return await anomaly_detector.flag_transaction(merchant, amount)

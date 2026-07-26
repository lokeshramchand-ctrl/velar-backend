from datetime import datetime, timezone
from typing import Dict, Any, List
from database.mongo import db

class SpendingPatternsEngine:
    async def get_category_breakdown(self, user_id: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Aggregates total spending by category for a specific timeframe."""
        pipeline = [
            {"$match": {
                "user_id": user_id,
                "timestamp": {"$gte": start_date, "$lte": end_date}
            }},
            {"$group": {
                "_id": "$category",
                "total_amount": {"$sum": "$amount"},
                "transaction_count": {"$sum": 1}
            }},
            {"$sort": {"total_amount": -1}}
        ]
        
        cursor = db.transactions.aggregate(pipeline)
        return [{"category": doc["_id"] or "Unknown", "total_amount": doc["total_amount"], "count": doc["transaction_count"]} async for doc in cursor]

    async def get_merchant_frequency(self, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Identifies the most frequently visited merchants."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": "$merchant",
                "visit_count": {"$sum": 1},
                "total_spent": {"$sum": "$amount"}
            }},
            {"$sort": {"visit_count": -1}},
            {"$limit": limit}
        ]
        cursor = db.transactions.aggregate(pipeline)
        return [{"merchant": doc["_id"], "visits": doc["visit_count"], "spent": doc["total_spent"]} async for doc in cursor]

spending_patterns = SpendingPatternsEngine()

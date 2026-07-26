from datetime import datetime
from typing import Dict, Any
from database.mongo import db

class TrendAnalyzer:
    async def calculate_mom_growth(self, user_id: str, current_month: int, current_year: int) -> Dict[str, Any]:
        """Calculates Month-over-Month (MoM) spending velocity."""
        # Note: In production, use robust date parsing. 
        # This is simplified for pipeline illustration.
        
        # Calculate current month spend
        curr_start = datetime(current_year, current_month, 1)
        curr_pipeline = [
            {"$match": {"user_id": user_id, "timestamp": {"$gte": curr_start}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        
        curr_res = await db.transactions.aggregate(curr_pipeline).to_list(length=1)
        curr_total = curr_res[0]["total"] if curr_res else 0.0
        
        # Mock previous month total for calculation
        prev_total = 15000.0 # Replace with actual DB query
        
        if prev_total == 0:
            growth = 0.0
        else:
            growth = ((curr_total - prev_total) / prev_total) * 100
            
        return {
            "current_spend": curr_total,
            "previous_spend": prev_total,
            "mom_growth_percentage": round(growth, 2),
            "trend": "up" if growth > 0 else "down"
        }

trend_analyzer = TrendAnalyzer()

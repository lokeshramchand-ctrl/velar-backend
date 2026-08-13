from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.jwt_auth import get_current_user
from feedback.feedback_service import feedback_service
from feedback.retraining_queue import retraining_manager
from models.schemas import User
from repositories.transaction_repository import transaction_repo

router = APIRouter(prefix="/v1/feedback", tags=["Continuous Learning"])

class FeedbackRequest(BaseModel):
    transaction_id: str = Field(..., min_length=1, max_length=100)
    original_prediction: str = Field(..., min_length=1, max_length=100)
    corrected_category: str = Field(..., min_length=1, max_length=100)
    confidence: float = Field(..., ge=0.0, le=1.0)

@router.post("/")
async def submit_feedback(
    request: FeedbackRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)
):
    """
    Accepts human feedback, updates the Active Learning queue,
    and asynchronously checks if the model needs retraining.
    """
    # 0. transaction_id is client-supplied - confirm it's actually this
    # user's transaction before recording anything against it or the
    # merchant-wide category correction it can trigger (see
    # feedback_service.process_feedback). 404s rather than 403s to match
    # this codebase's can't-distinguish-existence posture elsewhere
    # (routers/statements.py, routers/jobs.py).
    if await transaction_repo.get_by_id(request.transaction_id, current_user.id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    # 1. Process and save the feedback
    result = await feedback_service.process_feedback(
        transaction_id=request.transaction_id,
        original_prediction=request.original_prediction,
        corrected_category=request.corrected_category,
        confidence=request.confidence,
        user_id=current_user.id,
    )

    # 2. Check the queue threshold in the background (so we don't block the API response)
    if result["is_correction"]:
        background_tasks.add_task(retraining_manager.trigger_retraining_if_needed)

    return {"status": "success", "feedback_recorded": result["is_correction"]}

from fastapi import APIRouter
from pydantic import BaseModel
from rag.retriever import context_retriever
from rag.context_builder import context_builder
from rag.generator import explanation_generator

router = APIRouter(prefix="/v1", tags=["Explainability"])

class ExplainRequest(BaseModel):
    transaction_text: str
    target_question: str = "Why was this transaction categorized this way?"

@router.post("/explain")
async def explain_transaction(request: ExplainRequest):
    """
    RAG Pipeline: Retrieves behavioral vectors and generates a strict, grounded explanation.
    """
    # 1. Retrieve
    raw_context = await context_retriever.fetch_grounded_context(request.transaction_text)
    
    # 2. Build
    formatted_context = context_builder.build_prompt_string(raw_context)
    
    # 3. Generate
    explanation = await explanation_generator.generate_explanation(
        query=request.target_question,
        context_string=formatted_context
    )
    
    return {
        "query": request.transaction_text,
        "retrieved_documents": len(raw_context),
        "result": explanation
    }

"""Search endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from services.api.models import AnswerRequest, AnswerResponse, CitationModel, SearchRequest, SearchResponse, SearchResultModel
from services.api.services.answer_generator import AnswerGenerator
from services.api.services.search_engine import SearchEngine

router = APIRouter(prefix="/api", tags=["search"])


@router.post(
    "/search",
    responses={503: {"description": "Search service is unavailable"}},
)
def search(request: Request, payload: SearchRequest) -> SearchResponse:
    search_engine: SearchEngine | None = getattr(request.app.state, "search_engine", None)
    if search_engine is None:
        raise HTTPException(status_code=503, detail="Search service is unavailable")

    items = search_engine.search(
        query=payload.query,
        k=payload.k,
        domain_filter=payload.domain_filter,
        min_score=payload.min_score,
    )

    return SearchResponse(
        query=payload.query,
        results=[
            SearchResultModel(
                chunk_id=item["chunk_id"],
                text=item["text"],
                source_path=item["source_path"],
                domain=item["domain"],
                section=item["section"],
                relevance_score=item["relevance_score"],
            )
            for item in items
        ],
    )


@router.post(
    "/answer",
    response_model=AnswerResponse,
    responses={503: {"description": "Answer service is unavailable"}},
)
def answer(request: Request, payload: AnswerRequest) -> AnswerResponse:
    search_engine: SearchEngine | None = getattr(request.app.state, "search_engine", None)
    answer_generator: AnswerGenerator | None = getattr(request.app.state, "answer_generator", None)
    if search_engine is None or answer_generator is None:
        raise HTTPException(status_code=503, detail="Answer service is unavailable")

    items = search_engine.search(
        query=payload.query,
        k=payload.k,
        domain_filter=payload.domain_filter,
        min_score=0.0,
    )

    try:
        generated = answer_generator.generate(
            query=payload.query,
            context_chunks=items,
            max_tokens=payload.max_tokens,
        )
    except RuntimeError:
        generated = {
            "answer_text": "INSUFFICIENT_CONTEXT",
            "citations": [],
            "context_chunks": items,
            "model": answer_generator.model,
            "generation_time_ms": 0,
        }

    return AnswerResponse(
        query=payload.query,
        answer_text=generated["answer_text"],
        citations=[
            CitationModel(
                chunk_id=item["chunk_id"],
                source_path=item["source_path"],
                domain=item["domain"],
                section=item["section"],
                relevance_score=item["relevance_score"],
            )
            for item in generated["citations"]
        ],
        context_chunks=[
            SearchResultModel(
                chunk_id=item["chunk_id"],
                text=item["text"],
                source_path=item["source_path"],
                domain=item["domain"],
                section=item["section"],
                relevance_score=item["relevance_score"],
            )
            for item in generated.get("context_chunks", items)
        ],
        model=generated["model"],
        generation_time_ms=generated["generation_time_ms"],
    )

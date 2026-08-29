from fastapi import APIRouter, HTTPException, Request

from app.core.exceptions import AppError
from app.schemas.extract import ExtractRequest, ExtractResponse
from app.services.extract import extract_from_url

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/extract", response_model=ExtractResponse)
async def extract_document(payload: ExtractRequest, request: Request) -> ExtractResponse:
    settings = request.app.state.settings
    try:
        document = await extract_from_url(str(payload.url), settings)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return ExtractResponse(
        url=document.url,
        final_url=document.final_url,
        title=document.title,
        text=document.text,
        char_count=len(document.text),
        content_type=document.content_type,
    )

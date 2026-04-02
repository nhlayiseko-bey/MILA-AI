from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.security import verify_internal_api_key
from app.models.schemas import ConsentLogRequest, ScoreProcessingRequest, TriggerGenerationRequest
from app.runtime import gateway_processor


router = APIRouter()


@router.post("/triggers/generate", dependencies=[Depends(verify_internal_api_key)])
async def generate_trigger(request: TriggerGenerationRequest) -> JSONResponse:
    result = await gateway_processor.create_trigger_and_deliver(request=request)
    return JSONResponse(content=result.model_dump(mode="json"))


@router.post("/scores/process", dependencies=[Depends(verify_internal_api_key)])
async def process_score(request: ScoreProcessingRequest) -> JSONResponse:
    result = await gateway_processor.process_score_result(
        employee_uuid=request.employee_uuid,
        result=request.result,
        trigger_event_uuid=request.trigger_event_uuid,
        triggered_rule_id=request.triggered_rule_id,
    )
    return JSONResponse(content=result)


@router.post("/consent/log", dependencies=[Depends(verify_internal_api_key)])
async def log_consent(request: ConsentLogRequest) -> JSONResponse:
    result = await gateway_processor.record_consent(request=request)
    return JSONResponse(content=result)

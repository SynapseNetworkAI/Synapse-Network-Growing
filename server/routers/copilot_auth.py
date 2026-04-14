from fastapi import APIRouter

from server.schemas import (
    CopilotAuthStatus,
    CopilotDeviceCodeRequest,
    CopilotDeviceCodeOut,
    CopilotDeviceCodePollRequest,
    CopilotDeviceCodePollOut,
)
from server.services.runtime.copilot_auth import CopilotAuthService

router = APIRouter(prefix="/api/copilot-auth", tags=["copilot-auth"])
auth_service = CopilotAuthService()


@router.get("/status", response_model=CopilotAuthStatus)
def copilot_auth_status():
    return auth_service.get_status()


@router.post("/device-code", response_model=CopilotDeviceCodeOut)
def request_copilot_device_code(body: CopilotDeviceCodeRequest):
    return auth_service.request_device_code(host=body.host)


@router.post("/device-code/poll", response_model=CopilotDeviceCodePollOut)
def poll_copilot_device_code(body: CopilotDeviceCodePollRequest):
    return auth_service.poll_access_token_once(
        device_code=body.device_code,
        host=body.host,
        client_id=body.client_id,
    )
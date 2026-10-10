from typing import Annotated

from fastapi import APIRouter, Depends, status

from kontor.api.dependencies import get_agent_service
from kontor.api.schemas import AskRequest, AskResponse
from kontor.application.agent import AgentService

router = APIRouter()


@router.post("/agent/ask")
def ask(
    request: AskRequest, service: Annotated[AgentService, Depends(get_agent_service)]
) -> AskResponse:
    """Answer a question with the text-to-SQL agent (CONTRACT §16)."""
    conversation_id, answer = service.ask(request.question, request.conversation_id)
    return AskResponse.from_domain(conversation_id, answer)


@router.delete("/agent/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def forget(
    conversation_id: str, service: Annotated[AgentService, Depends(get_agent_service)]
) -> None:
    service.forget(conversation_id)

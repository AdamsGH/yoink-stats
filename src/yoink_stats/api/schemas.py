"""Stats API schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    message_id: int
    date: datetime
    from_user: int | None
    msg_type: str
    text: str | None

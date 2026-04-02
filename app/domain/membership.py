from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MembershipCheckState(StrEnum):
    MEMBER = "member"
    NOT_MEMBER = "not_member"
    BOT_NO_ACCESS = "bot_no_access"
    CHAT_UNAVAILABLE = "chat_unavailable"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass(frozen=True)
class MembershipResult:
    state: MembershipCheckState
    status: str | None = None
    detail: str | None = None

    @property
    def is_member(self) -> bool:
        return self.state == MembershipCheckState.MEMBER

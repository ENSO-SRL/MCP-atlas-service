from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from src.mcp.domain.enums.mcp_enums import NoticeStatus, NoticeType


@dataclass
class BookingNotice:
    """
    Entidad BookingNotice (hija de BookingRequest).
    Modela un aviso, discrepancia o solicitud de confirmación específica levantada
    sobre la reserva antes o durante su confirmación definitiva.
    """
    id: UUID = field(default_factory=uuid4)
    booking_id: UUID = field(default_factory=uuid4)
    notice_type: NoticeType = NoticeType.PRICE_DISCREPANCY
    status: NoticeStatus = NoticeStatus.PENDING
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    requires_action: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    resolution_action: Optional[str] = None


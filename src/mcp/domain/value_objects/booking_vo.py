from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from src.mcp.domain.enums.mcp_enums import CalculationBasis
from src.shared.domain.base import ValueObject


@dataclass(frozen=True)
class IdempotencyKey(ValueObject):
    """
    Clave de idempotencia provista por el cliente (Claude) junto con el fingerprint del payload.
    Previene re-procesamiento de solicitudes y detecta conflictos si el payload cambia.
    """
    key: str
    fingerprint: str

    @classmethod
    def create(cls, key: str, payload: dict[str, Any]) -> IdempotencyKey:
        if not key or not key.strip():
            raise ValueError("La clave de idempotencia no puede ser vacía.")
        canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        fingerprint = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        return cls(key=key.strip(), fingerprint=fingerprint)


@dataclass(frozen=True)
class PriceEstimate(ValueObject):
    """
    Estimado de precio informativo para un slot o reserva.
    Cumple con la directriz de Anthropic: precio siempre informativo (informative: True).
    """
    amount: Decimal
    currency: str = "DOP"
    basis: CalculationBasis = CalculationBasis.PER_BOOKING
    label: str = "Tarifa estándar"
    rule_id: Optional[UUID] = None
    informative: bool = True
    note: str = "Precio informativo; el establecimiento confirma la cotización final."

    def to_dict(self) -> dict[str, Any]:
        return {
            "amount": float(self.amount),
            "currency": self.currency,
            "basis": self.basis.value,
            "label": self.label,
            "informative": self.informative,
            "note": self.note,
        }

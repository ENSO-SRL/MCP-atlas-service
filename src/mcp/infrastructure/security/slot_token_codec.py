from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Any
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from src.mcp.domain.exceptions.mcp_exceptions import (
    SlotTokenExpiredException,
    SlotTokenInvalidException,
)
from src.mcp.domain.value_objects.slot_token import SlotToken
from src.shared.config.settings import get_settings


class SlotTokenCodec:
    """
    Codec y validador criptográfico para el Value Object SlotToken.
    Utiliza cifrado simétrico autenticado (AES-128-CBC + HMAC-SHA256 vía Fernet)
    con clave derivada de forma determinista desde MCP_TOKEN_SECRET.

    Garantías de seguridad:
    1. Claude no puede alterar fechas, recurso, versión ni servicio (inmutabilidad).
    2. El token está estrictamente acotado en el tiempo (expiración comprobada).
    3. Vinculación estricta al usuario autenticado (sub == user_uuid).
    """

    def __init__(self, secret: Optional[str] = None):
        raw_secret = secret or get_settings().MCP_TOKEN_SECRET
        # Derivamos una clave URL-safe de 32 bytes para Fernet mediante SHA-256
        derived_key = hashlib.sha256(raw_secret.encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(derived_key)
        self._fernet = Fernet(fernet_key)

    def encode(
        self,
        token_id: str,
        user_uuid: UUID,
        offer_ref: str,
        service_id: int,
        slot_start: datetime,
        slot_end: Optional[datetime],
        contract_version: str,
        expires_at: datetime,
        applied_filters: Optional[dict[str, Any]] = None,
        is_estimated: bool = False,
    ) -> SlotToken:
        """
        Genera y cifra el token de oferta produciendo un SlotToken válido con raw_token.
        """
        payload = {
            "token_id": token_id,
            "user_uuid": str(user_uuid),
            "offer_ref": offer_ref,
            "service_id": service_id,
            "slot_start": slot_start.isoformat(),
            "slot_end": slot_end.isoformat() if slot_end else None,
            "contract_version": contract_version,
            "expires_at": expires_at.isoformat(),
            "applied_filters": applied_filters or {},
            "is_estimated": is_estimated,
        }
        serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        raw_token = self._fernet.encrypt(serialized.encode("utf-8")).decode("utf-8")

        return SlotToken(
            token_id=token_id,
            user_uuid=user_uuid,
            offer_ref=offer_ref,
            service_id=service_id,
            slot_start=slot_start,
            slot_end=slot_end,
            contract_version=contract_version,
            expires_at=expires_at,
            raw_token=raw_token,
            applied_filters=applied_filters or {},
            is_estimated=is_estimated,
        )

    def decode(self, raw_token: str, now: Optional[datetime] = None) -> SlotToken:
        """
        Descifra y valida la firma del raw_token.
        Lanza SlotTokenInvalidException si fue alterado o es ilegible.
        Lanza SlotTokenExpiredException si ha superado su tiempo de vida.
        """
        try:
            decrypted_bytes = self._fernet.decrypt(raw_token.encode("utf-8"))
        except InvalidToken:
            raise SlotTokenInvalidException(
                "El token de oferta es inválido, manipulado o fue firmado con otra clave."
            )
        except Exception as e:
            raise SlotTokenInvalidException(f"Error procesando token de oferta: {str(e)}")

        try:
            payload = json.loads(decrypted_bytes.decode("utf-8"))
            token_id = str(payload["token_id"])
            user_uuid = UUID(payload["user_uuid"])
            offer_ref = str(payload["offer_ref"])
            service_id = int(payload["service_id"])
            slot_start = datetime.fromisoformat(payload["slot_start"])
            slot_end = (
                datetime.fromisoformat(payload["slot_end"])
                if payload.get("slot_end")
                else None
            )
            contract_version = str(payload["contract_version"])
            expires_at = datetime.fromisoformat(payload["expires_at"])
            applied_filters = payload.get("applied_filters", {})
            is_estimated = bool(payload.get("is_estimated", False))
        except (KeyError, ValueError, TypeError) as e:
            raise SlotTokenInvalidException(f"Estructura interna de token corrupta: {str(e)}")

        current_time = now or datetime.now(timezone.utc)
        if current_time > expires_at:
            raise SlotTokenExpiredException(
                "El token de oferta ha expirado. Consulta disponibilidad nuevamente para obtener una oferta vigente."
            )

        return SlotToken(
            token_id=token_id,
            user_uuid=user_uuid,
            offer_ref=offer_ref,
            service_id=service_id,
            slot_start=slot_start,
            slot_end=slot_end,
            contract_version=contract_version,
            expires_at=expires_at,
            raw_token=raw_token,
            applied_filters=applied_filters,
            is_estimated=is_estimated,
        )

    def verify_for_user(self, token: SlotToken, expected_user_uuid: UUID) -> None:
        """
        Valida que el token pertenezca al usuario actualmente autenticado (sub).
        Lanza SlotTokenInvalidException si hay discrepancia.
        """
        if not token.is_valid_for_user(expected_user_uuid):
            raise SlotTokenInvalidException(
                f"El token de oferta no pertenece al usuario autenticado ({expected_user_uuid})."
            )

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.mcp.domain.exceptions.mcp_exceptions import (
    SlotTokenExpiredException,
    SlotTokenInvalidException,
)
from src.mcp.infrastructure.security.slot_token_codec import SlotTokenCodec


def test_slot_token_encode_decode_happy_path():
    codec = SlotTokenCodec(secret="test-secret-key-1234567890")
    user_uuid = uuid4()
    slot_start = datetime.now(timezone.utc) + timedelta(days=1)
    slot_end = slot_start + timedelta(hours=1, minutes=30)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    token = codec.encode(
        token_id="tok_abc123",
        user_uuid=user_uuid,
        offer_ref="off_court_1_morning",
        service_id=10,
        slot_start=slot_start,
        slot_end=slot_end,
        contract_version="2026-10-26.1",
        expires_at=expires_at,
    )

    assert token.token_id == "tok_abc123"
    assert token.user_uuid == user_uuid
    assert token.offer_ref == "off_court_1_morning"
    assert token.service_id == 10
    assert token.contract_version == "2026-10-26.1"
    assert token.raw_token is not None

    # Decodificar el raw_token generado
    decoded = codec.decode(token.raw_token)
    assert decoded.token_id == "tok_abc123"
    assert decoded.user_uuid == user_uuid
    assert decoded.offer_ref == "off_court_1_morning"
    assert decoded.service_id == 10
    assert decoded.contract_version == "2026-10-26.1"
    assert decoded.raw_token == token.raw_token

    # Validar coincidencia de usuario
    codec.verify_for_user(decoded, user_uuid)


def test_slot_token_user_mismatch_raises():
    codec = SlotTokenCodec(secret="test-secret-key-1234567890")
    user_owner = uuid4()
    impostor_user = uuid4()

    token = codec.encode(
        token_id="tok_owner",
        user_uuid=user_owner,
        offer_ref="off_padel_2",
        service_id=5,
        slot_start=datetime.now(timezone.utc) + timedelta(hours=2),
        slot_end=None,
        contract_version="v1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    decoded = codec.decode(token.raw_token)
    with pytest.raises(SlotTokenInvalidException) as exc_info:
        codec.verify_for_user(decoded, impostor_user)
    assert "no pertenece al usuario autenticado" in str(exc_info.value)


def test_slot_token_expired_raises():
    codec = SlotTokenCodec(secret="test-secret-key-1234567890")
    user_uuid = uuid4()
    # Expirado hace 5 minutos
    expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)

    token = codec.encode(
        token_id="tok_expired",
        user_uuid=user_uuid,
        offer_ref="off_expired",
        service_id=8,
        slot_start=datetime.now(timezone.utc) + timedelta(hours=1),
        slot_end=None,
        contract_version="v1",
        expires_at=expires_at,
    )

    with pytest.raises(SlotTokenExpiredException):
        codec.decode(token.raw_token)


def test_slot_token_tampered_raises():
    codec = SlotTokenCodec(secret="test-secret-key-1234567890")
    token = codec.encode(
        token_id="tok_tampered",
        user_uuid=uuid4(),
        offer_ref="off_tampered",
        service_id=8,
        slot_start=datetime.now(timezone.utc) + timedelta(hours=1),
        slot_end=None,
        contract_version="v1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )

    # Alterar un caracter del token cifrado
    tampered_raw = token.raw_token[:-4] + "X9Y8"
    with pytest.raises(SlotTokenInvalidException):
        codec.decode(tampered_raw)


def test_slot_token_wrong_secret_key_raises():
    codec_a = SlotTokenCodec(secret="secret-key-AAAA")
    codec_b = SlotTokenCodec(secret="secret-key-BBBB")

    token = codec_a.encode(
        token_id="tok_secret",
        user_uuid=uuid4(),
        offer_ref="off_secret",
        service_id=1,
        slot_start=datetime.now(timezone.utc) + timedelta(hours=1),
        slot_end=None,
        contract_version="v1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )

    with pytest.raises(SlotTokenInvalidException):
        codec_b.decode(token.raw_token)

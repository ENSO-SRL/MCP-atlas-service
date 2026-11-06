from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest

from src.mcp.application.dto.booking_dtos import ResolveBookingNoticeInputDTO
from src.mcp.application.use_cases.resolve_booking_notice import ResolveBookingNoticeUseCase
from src.mcp.domain.entities.booking_request import BookingRequest
from src.mcp.domain.enums.mcp_enums import (
    BookingStatus,
    CalculationBasis,
    NoticeStatus,
    NoticeType,
)
from src.mcp.domain.events.booking_events import (
    BookingNoticeRaisedEvent,
    BookingRejectedEvent,
    BookingResumedEvent,
)
from src.mcp.domain.exceptions.mcp_exceptions import (
    EntityNotFoundException,
    InvalidStateTransitionException,
)
from src.mcp.domain.value_objects.booking_vo import PriceEstimate
from src.mcp.infrastructure.workers.inbox_consumer_worker import InboxConsumerWorker


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _build_sample_booking(user_uuid=None, status=BookingStatus.REQUESTED) -> BookingRequest:
    return BookingRequest(
        id=uuid4(),
        user_uuid=user_uuid or uuid4(),
        service_id=18,
        contract_version_id=uuid4(),
        status=status,
        idempotency_key="idemp_notice_test",
        request_fingerprint="fp_notice_test",
        price_estimate=PriceEstimate(
            amount=Decimal("1800.00"),
            currency="DOP",
            basis=CalculationBasis.PER_BOOKING,
            label="Tarifa Valle",
            informative=True,
            note="Precio estimado",
        ),
        expires_at=datetime.now(timezone.utc),
    )


def test_raise_notice_pauses_booking_and_records_event():
    booking = _build_sample_booking(status=BookingStatus.REQUESTED)

    notice = booking.raise_notice(
        notice_type=NoticeType.PRICE_DISCREPANCY,
        message="Ajuste de precio: el club cobra RD$ 2,000 en vez de RD$ 1,800",
        payload={"expected_total": 1800.0, "actual_total": 2000.0, "currency": "DOP"},
        requires_action=True,
    )

    assert booking.status == BookingStatus.REQUIRES_CONFIRMATION
    assert booking.status_reason == "Ajuste de precio: el club cobra RD$ 2,000 en vez de RD$ 1,800"
    assert len(booking.notices) == 1
    assert notice.status == NoticeStatus.PENDING
    assert notice.notice_type == NoticeType.PRICE_DISCREPANCY

    events = booking.pull_domain_events()
    assert any(isinstance(e, BookingNoticeRaisedEvent) for e in events)


def test_raise_notice_without_required_action_does_not_pause():
    booking = _build_sample_booking(status=BookingStatus.ACCEPTED)

    notice = booking.raise_notice(
        notice_type=NoticeType.GENERAL_NOTICE,
        message="Recordatorio: uso obligatorio de calzado de pádel",
        requires_action=False,
    )

    assert booking.status == BookingStatus.ACCEPTED
    assert notice.status == NoticeStatus.PENDING
    assert notice.requires_action is False


def test_resolve_notice_accept_resumes_booking_and_updates_price():
    booking = _build_sample_booking(status=BookingStatus.REQUESTED)
    notice = booking.raise_notice(
        notice_type=NoticeType.PRICE_DISCREPANCY,
        message="Tarifa actualizada a RD$ 2,000",
        payload={"expected_total": 1800.0, "actual_total": 2000.0, "currency": "DOP"},
        requires_action=True,
    )
    booking.pull_domain_events()  # Limpiar eventos previos

    resolved_ids = booking.resolve_notice(decision="accept", notice_id=notice.id)

    assert resolved_ids == [notice.id]
    assert notice.status == NoticeStatus.ACCEPTED
    assert notice.resolution_action == "accepted"
    assert booking.status == BookingStatus.ACCEPTED
    assert booking.price_estimate.amount == Decimal("2000.0")

    events = booking.pull_domain_events()
    assert any(isinstance(e, BookingResumedEvent) for e in events)


def test_resolve_notice_reject_marks_booking_as_rejected():
    booking = _build_sample_booking(status=BookingStatus.REQUESTED)
    notice = booking.raise_notice(
        notice_type=NoticeType.PRICE_DISCREPANCY,
        message="Tarifa actualizada",
        payload={"expected_total": 1800.0, "actual_total": 2500.0},
        requires_action=True,
    )
    booking.pull_domain_events()

    resolved_ids = booking.resolve_notice(decision="reject", notice_id=notice.id)

    assert resolved_ids == [notice.id]
    assert notice.status == NoticeStatus.REJECTED
    assert notice.resolution_action == "rejected"
    assert booking.status == BookingStatus.REJECTED

    events = booking.pull_domain_events()
    assert any(isinstance(e, BookingRejectedEvent) for e in events)


def test_resolve_notice_partial_acceptance_keeps_requires_confirmation():
    booking = _build_sample_booking(status=BookingStatus.REQUESTED)
    notice_1 = booking.raise_notice(
        notice_type=NoticeType.PRICE_DISCREPANCY,
        message="Aviso 1",
        requires_action=True,
    )
    notice_2 = booking.raise_notice(
        notice_type=NoticeType.SCHEDULE_SHIFT,
        message="Aviso 2",
        requires_action=True,
    )

    # Aceptar solo el primer aviso
    booking.resolve_notice(decision="accept", notice_id=notice_1.id)

    assert notice_1.status == NoticeStatus.ACCEPTED
    assert notice_2.status == NoticeStatus.PENDING
    assert booking.status == BookingStatus.REQUIRES_CONFIRMATION

    # Aceptar el segundo aviso -> ahora sí reanuda a ACCEPTED
    booking.resolve_notice(decision="accept", notice_id=notice_2.id)
    assert notice_2.status == NoticeStatus.ACCEPTED
    assert booking.status == BookingStatus.ACCEPTED


def test_resolve_notice_invalid_status_raises():
    booking = _build_sample_booking(status=BookingStatus.CONFIRMED)
    with pytest.raises(InvalidStateTransitionException):
        booking.resolve_notice(decision="accept")


@pytest.mark.anyio
async def test_resolve_booking_notice_use_case_happy_path_accept():
    user_uuid = uuid4()
    booking = _build_sample_booking(user_uuid=user_uuid, status=BookingStatus.REQUESTED)
    notice = booking.raise_notice(
        notice_type=NoticeType.PRICE_DISCREPANCY,
        message="Ajuste de precio",
        payload={"actual_total": 2200.0},
        requires_action=True,
    )

    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_id = AsyncMock(return_value=booking)
    mock_booking_repo.save = AsyncMock(side_effect=lambda b: b)

    mock_outbox_repo = MagicMock()
    mock_outbox_repo.record_event = AsyncMock()

    mock_catalog_repo = MagicMock()
    mock_catalog_svc = MagicMock()
    mock_catalog_svc.combo_code = "GROVE_PADEL"
    mock_catalog_repo.get_by_id = AsyncMock(return_value=mock_catalog_svc)

    use_case = ResolveBookingNoticeUseCase(
        booking_repo=mock_booking_repo,
        outbox_repo=mock_outbox_repo,
        catalog_repo=mock_catalog_repo,
    )

    query = ResolveBookingNoticeInputDTO(
        booking_id=booking.id,
        user_uuid=user_uuid,
        decision="accept",
        notice_id=notice.id,
        user_phone="+18095551234",
        user_email="user@test.com",
    )

    result = await use_case.execute(query)

    assert result.status == BookingStatus.ACCEPTED.value
    assert result.decision == "accept"
    assert result.resolved_notice_ids == [notice.id]
    mock_outbox_repo.record_event.assert_awaited_once()
    call_args = mock_outbox_repo.record_event.call_args[1]
    assert call_args["event_type"] == "BookingResumed"
    assert call_args["payload"]["combo_code"] == "GROVE_PADEL"
    assert call_args["payload"]["projected_total"] == 2200.0


@pytest.mark.anyio
async def test_resolve_booking_notice_use_case_forbidden_user():
    user_owner = uuid4()
    attacker = uuid4()
    booking = _build_sample_booking(user_uuid=user_owner, status=BookingStatus.REQUIRES_CONFIRMATION)

    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_id = AsyncMock(return_value=booking)
    mock_outbox_repo = MagicMock()

    use_case = ResolveBookingNoticeUseCase(
        booking_repo=mock_booking_repo,
        outbox_repo=mock_outbox_repo,
    )

    query = ResolveBookingNoticeInputDTO(
        booking_id=booking.id,
        user_uuid=attacker,
        decision="accept",
    )

    with pytest.raises(EntityNotFoundException):
        await use_case.execute(query)


@pytest.mark.anyio
async def test_inbox_consumer_worker_handles_booking_notice_raised():
    import json
    from unittest.mock import patch

    booking = _build_sample_booking(status=BookingStatus.ACCEPTED)

    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.get = AsyncMock(return_value=None)  # No procesado aún
    mock_session.begin.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=booking)
    mock_repo.save = AsyncMock(side_effect=lambda b: b)

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = None

    mock_redis = AsyncMock()
    mock_redis.xack = AsyncMock()
    mock_hold_manager = AsyncMock()

    worker = InboxConsumerWorker(
        redis_client=mock_redis,
        session_factory=mock_session_factory,
        hold_manager=mock_hold_manager,
    )

    notice_uuid = uuid4()
    raw_fields = {
        "payload": json.dumps({
            "event_id": str(uuid4()),
            "event_type": "BookingNoticeRaised",
            "aggregate_id": str(booking.id),
            "payload": {
                "notice_id": str(notice_uuid),
                "notice_type": "price_discrepancy",
                "message": "Ajuste tarifario del club",
                "details": {"expected_total": 1800.0, "actual_total": 2100.0},
                "requires_action": True,
            },
        })
    }

    with patch(
        "src.mcp.infrastructure.workers.inbox_consumer_worker.SqlBookingRepository",
        return_value=mock_repo,
    ):
        success = await worker.process_message("msg-1", raw_fields)

    assert success is True
    assert booking.status == BookingStatus.REQUIRES_CONFIRMATION
    assert len(booking.notices) == 1
    assert booking.notices[0].id == notice_uuid
    mock_hold_manager.release_hold.assert_not_awaited()


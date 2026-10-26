from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import pytest
from uuid import uuid4

from src.mcp.domain.entities.booking_request import BookingRequest
from src.mcp.domain.entities.catalog_entities import Establishment
from src.mcp.domain.entities.contract_entities import (
    ContractDimension,
    ServiceContractVersion,
)
from src.mcp.domain.entities.service_price_rule import ServicePriceRule
from src.mcp.domain.enums.mcp_enums import (
    AvailabilityPattern,
    BookingStatus,
    CalculationBasis,
    ContractStatus,
    DimensionApplyMode,
    DimensionValuesSource,
    RuleType,
)
from src.mcp.domain.exceptions.mcp_exceptions import (
    ContractValidationException,
    InvalidStateTransitionException,
)
from src.mcp.domain.value_objects.canonical_filter_hash import CanonicalFilterHash


def test_booking_request_state_machine_happy_path():
    user_uuid = uuid4()
    booking = BookingRequest.create(
        user_uuid=user_uuid,
        service_id=10,
        contract_version_id=uuid4(),
        idempotency_key="idemp_1",
        request_fingerprint="fp_1",
        token_id="tok_1",
        offer_ref="off_1",
        slot_start=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    assert booking.status == BookingStatus.REQUESTED
    events = booking.pull_domain_events()
    assert len(events) == 1

    # Confirmación
    booking.confirm(external_ref="EXT-12345", assigned_details={"cancha": "2"})
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.external_ref == "EXT-12345"

    # Solicitud de cancelación
    booking.request_cancellation(reason="Cambio de planes")
    assert booking.status == BookingStatus.CANCEL_REQUESTED

    # Confirmación de cancelación
    booking.confirm_cancellation()
    assert booking.status == BookingStatus.CANCELLED


def test_booking_request_late_confirmation_rule():
    # Si la solicitud venció (EXPIRED), pero el negocio confirma tarde, la confirmación manda
    booking = BookingRequest.create(
        user_uuid=uuid4(),
        service_id=10,
        contract_version_id=uuid4(),
        idempotency_key="idemp_late",
        request_fingerprint="fp_late",
        token_id="tok_late",
        offer_ref="off_late",
        slot_start=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )
    booking.expire()
    assert booking.status == BookingStatus.EXPIRED

    # Transición permitida por regla de negocio
    booking.confirm(external_ref="LATE-CONFIRM-999")
    assert booking.status == BookingStatus.CONFIRMED


def test_booking_request_invalid_transition_raises():
    booking = BookingRequest.create(
        user_uuid=uuid4(),
        service_id=10,
        contract_version_id=uuid4(),
        idempotency_key="idemp_err",
        request_fingerprint="fp_err",
        token_id="tok_err",
        offer_ref="off_err",
        slot_start=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )
    booking.reject(reason="Sin cupos")
    assert booking.status == BookingStatus.REJECTED

    # No se puede pasar de REJECTED a CONFIRMED
    with pytest.raises(InvalidStateTransitionException):
        booking.confirm(external_ref="FAIL")


def test_canonical_filter_hash_determinism():
    filters_a = {"date": "2026-10-23", "court": "cancha-1", "party_size": 4}
    filters_b = {"party_size": 4, "court": "cancha-1", "date": "2026-10-23"}

    hash_a = CanonicalFilterHash.from_filters(filters_a)
    hash_b = CanonicalFilterHash.from_filters(filters_b)

    assert hash_a.hash_value == hash_b.hash_value
    assert hash_a.to_cache_key(5, "v1.0") == hash_b.to_cache_key(5, "v1.0")


def test_contract_dimension_cycle_detection():
    # Dimensión A depende de B, y B depende de A -> Ciclo
    dim_a = ContractDimension(
        id=uuid4(), key="dim_a", depends_on=["dim_b"],
        values_source=DimensionValuesSource.INLINE
    )
    dim_b = ContractDimension(
        id=uuid4(), key="dim_b", depends_on=["dim_a"],
        values_source=DimensionValuesSource.INLINE
    )

    contract = ServiceContractVersion(
        id=uuid4(),
        service_id=10,
        pattern=AvailabilityPattern.SLOT_OBJECT,
        dimensions=[dim_a, dim_b],
    )

    with pytest.raises(ContractValidationException, match="Ciclo detectado"):
        contract.publish()


def test_service_price_rule_evaluation():
    rule = ServicePriceRule(
        id=uuid4(),
        service_id=1,
        label="Tarifa Nocturna por Persona",
        weekdays=[1, 2, 3, 4, 5],  # Lunes a Viernes
        start_minute=1080,         # 18:00
        end_minute=1380,           # 23:00
        valid_from=date(2026, 1, 1),
        amount=Decimal("500.00"),
        calculation_basis=CalculationBasis.PER_PERSON,
    )

    # Lunes a las 19:30 (minuto 1170) -> Aplica
    dt_valid = datetime(2026, 10, 26, 19, 30)  # Lunes
    assert rule.is_applicable(dt_valid, party_size=4) is True
    estimate = rule.calculate_estimate(party_size=4)
    assert estimate.amount == Decimal("2000.00")
    assert estimate.basis == CalculationBasis.PER_PERSON

    # Domingo a las 19:30 -> No aplica (fin de semana)
    dt_sunday = datetime(2026, 10, 25, 19, 30)
    assert rule.is_applicable(dt_sunday, party_size=4) is False


def test_establishment_rule_type_anticipation():
    est_only_today = Establishment(
        id=1, name="Club Tenis", code="CT", rule_type=RuleType.ONLY_TODAY
    )
    today = date(2026, 10, 22)
    tomorrow = date(2026, 10, 23)
    past = date(2026, 10, 21)

    assert est_only_today.is_date_allowed(today, reference_date=today) is True
    assert est_only_today.is_date_allowed(tomorrow, reference_date=today) is False
    assert est_only_today.is_date_allowed(past, reference_date=today) is False

    est_tomorrow = Establishment(
        id=2, name="Padel Club", code="PC", rule_type=RuleType.TODAY_AND_TOMORROW
    )
    assert est_tomorrow.is_date_allowed(today, reference_date=today) is True
    assert est_tomorrow.is_date_allowed(tomorrow, reference_date=today) is True
    assert est_tomorrow.is_date_allowed(today + timedelta(days=2), reference_date=today) is False

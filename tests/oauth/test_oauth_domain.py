import base64
import hashlib
import pytest
from uuid import uuid4

from src.oauth.domain.entities.user import User
from src.oauth.domain.value_objects.phone_number_e164 import PhoneNumberE164
from src.oauth.domain.value_objects.email_address import EmailAddress
from src.oauth.domain.value_objects.pkce_challenge import PKCEChallenge
from src.oauth.domain.entities.authorization_code import AuthorizationCode


def test_user_profile_completeness_and_booking_permission():
    # Usuario nuevo sin confirmar y sin perfil completo
    user = User(
        id=1,
        uuid=uuid4(),
        email=EmailAddress("socio@club.com"),
        name="Carlos",
        last_name="Gomez",
        is_active=True,
        is_confirmed=False,
    )
    assert not user.is_profile_complete()
    assert not user.can_book()

    # Se completa el teléfono pero falta el género
    user.phone = PhoneNumberE164("+18095551234")
    assert not user.is_profile_complete()
    assert not user.can_book()

    # Se completa el género pero aún no confirma el email
    user.gender = "M"
    assert user.is_profile_complete()
    assert not user.can_book()

    # Se confirma el email -> ahora sí tiene permiso de reserva
    user.confirm_email()
    assert user.can_book()


def test_phone_number_e164_validation():
    # Válidos
    phone1 = PhoneNumberE164("+18095551234")
    assert str(phone1) == "+18095551234"
    phone2 = PhoneNumberE164("+34912345678")
    assert str(phone2) == "+34912345678"

    # Inválidos
    with pytest.raises(ValueError):
        PhoneNumberE164("8095551234")  # Sin '+'
    with pytest.raises(ValueError):
        PhoneNumberE164("+1")          # Demasiado corto


def test_pkce_challenge_s256_verification():
    # Verifier legítimo de 43 a 128 caracteres
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    
    # Generar challenge manualmente: Base64URL(SHA256(verifier)) sin padding
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge_str = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    challenge = PKCEChallenge(code_challenge=challenge_str, method="S256")
    
    # Debe ser True con el verifier correcto
    assert challenge.verify(verifier) is True
    # Debe ser False con un verifier incorrecto
    assert challenge.verify(verifier + "wrong") is False


def test_authorization_code_lifecycle():
    verifier = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge_str = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    code = AuthorizationCode(
        id="auth_code_test_123",
        client_id="claude-desktop",
        user_uuid=uuid4(),
        redirect_uri="https://claude.ai/oauth/callback",
        challenge=PKCEChallenge(challenge_str, "S256"),
    )

    assert not code.is_used()
    assert not code.is_expired()

    # Consumir con verifier inválido falla y no consume
    assert not code.consume("wrong-verifier-123456789012345678901234567890")
    assert not code.is_used()

    # Consumir con verifier correcto tiene éxito y lo marca como usado
    assert code.consume(verifier) is True
    assert code.is_used()

    # Reintentar consumirlo falla (un solo uso)
    assert not code.consume(verifier)


def test_user_credential_exclusivity():
    from src.oauth.domain.entities.user_credential import UserCredential

    # Válido: solo establecimiento
    cred_est = UserCredential(
        id=1,
        user_id=10,
        establishment_id=5,
        encrypted_data="enc_data",
        membership_number="SOCIO-1234",
    )
    assert cred_est.is_valid_for_establishment(5)
    assert not cred_est.is_valid_for_establishment(99)

    # Válido: solo servicio
    cred_srv = UserCredential(
        id=2,
        user_id=10,
        servicio_id=20,
        encrypted_data="enc_data",
        membership_number="CLUB-5678",
    )
    assert cred_srv.is_valid_for_service(20)

    # Inválido: ambos presentes (viola check constraint)
    with pytest.raises(ValueError, match="exclusivamente"):
        UserCredential(
            id=3,
            user_id=10,
            establishment_id=5,
            servicio_id=20,
            encrypted_data="enc_data",
        )

    # Inválido: ninguno presente (viola check constraint)
    with pytest.raises(ValueError, match="exclusivamente"):
        UserCredential(
            id=4,
            user_id=10,
            encrypted_data="enc_data",
        )


def test_refresh_token_lifecycle():
    from src.oauth.domain.entities.refresh_token import RefreshToken

    rt = RefreshToken(
        id="rt_hash_123",
        client_id="claude-web",
        user_uuid=uuid4(),
        scope="bookings:read bookings:write",
    )

    assert rt.is_valid()
    assert not rt.is_revoked()

    # Revocación
    rt.revoke()
    assert rt.is_revoked()
    assert not rt.is_valid()


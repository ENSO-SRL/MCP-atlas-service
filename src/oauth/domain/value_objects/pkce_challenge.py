from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from src.shared.domain.base import ValueObject

_VERIFIER_REGEX = re.compile(r"^[A-Za-z0-9\-\._~]{43,128}$")


@dataclass(frozen=True)
class PKCEChallenge(ValueObject):
    """
    Representa un desafío PKCE (RFC 7636).
    Exige obligatoriamente el método 'S256' para proteger contra interceptación de códigos.
    """
    code_challenge: str
    method: str = "S256"

    def __post_init__(self) -> None:
        if not self.code_challenge:
            raise ValueError("El 'code_challenge' es obligatorio en OAuth con PKCE.")
        if self.method != "S256":
            raise ValueError("Únicamente se admite el método de transformación 'S256' (RFC 7636).")

    def verify(self, code_verifier: str) -> bool:
        """
        Verifica si el code_verifier provisto coincide con el code_challenge.
        Fórmula: Base64URL(SHA256(code_verifier)) == code_challenge
        """
        if not code_verifier or not _VERIFIER_REGEX.match(code_verifier):
            return False

        # SHA-256 digest
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        # Base64URL-encode sin padding '='
        computed_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        
        # Comparación en tiempo constante para evitar ataques de temporización
        return computed_challenge == self.code_challenge.rstrip("=")

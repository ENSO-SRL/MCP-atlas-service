from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from src.shared.domain.base import ValueObject


@dataclass(frozen=True)
class CanonicalFilterHash(ValueObject):
    """
    Calcula y almacena el hash determinista SHA-256 para una combinación de filtros de disponibilidad.
    Garantiza que el orden de las claves no altere el valor de la clave de caché.
    """
    hash_value: str

    @classmethod
    def from_filters(cls, filters: dict[str, Any]) -> CanonicalFilterHash:
        """Normaliza los filtros ordenando claves y genera el hash SHA-256 canónico."""
        # Serialización compacta y canónica (sin espacios, claves ordenadas)
        canonical_json = json.dumps(filters, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        return cls(hash_value=digest)

    def to_cache_key(self, service_id: int, contract_version: str) -> str:
        """Construye la clave canónica de almacenamiento en Redis."""
        return f"avail:cache:{service_id}:{contract_version}:{self.hash_value}"

    def __str__(self) -> str:
        return self.hash_value

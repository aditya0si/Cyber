"""JWT access tokens (RS256, docs/15 §2.2).

Dev-mode key: an ephemeral RSA pair is generated at import time when no
`JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` env vars are set (see `cybersim.infra.config`).
Prod injects PEM keys via environment/secret manager.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from cybersim.infra.config import get_settings


class JWTMint:
    """Issue + verify RS256-signed access tokens."""

    def __init__(
        self,
        private_key_pem: str | None = None,
        public_key_pem: str | None = None,
        kid: str = "dev-1",
        issuer: str = "http://localhost:8000",
        access_ttl_sec: int = 900,
    ) -> None:
        if private_key_pem and public_key_pem:
            loaded_private = serialization.load_pem_private_key(
                private_key_pem.encode("utf-8"), password=None
            )
            loaded_public = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
            if not isinstance(loaded_private, rsa.RSAPrivateKey):
                raise ValueError("JWT_PRIVATE_KEY must be an RSA private key")
            if not isinstance(loaded_public, rsa.RSAPublicKey):
                raise ValueError("JWT_PUBLIC_KEY must be an RSA public key")
            self._private_key: rsa.RSAPrivateKey = loaded_private
            self._public_key: rsa.RSAPublicKey = loaded_public
        else:
            # dev fallback: ephemeral key
            dev_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            self._private_key = dev_private
            self._public_key = dev_private.public_key()
        self.kid = kid
        self.issuer = issuer
        self.access_ttl_sec = access_ttl_sec

    # ---- signing -----------------------------------------------------------
    def issue_access_token(
        self,
        *,
        user_id: str,
        org_id: str,
        org_role: str,
        scopes: list[str],
        session_id: str,
    ) -> str:
        now = datetime.now(tz=UTC)
        claims: dict[str, Any] = {
            "sub": user_id,
            "org_id": org_id,
            "org_role": org_role,
            "scopes": scopes,
            "sid": session_id,
            "typ": "access",
            "iss": self.issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self.access_ttl_sec)).timestamp()),
        }
        return jwt.encode(claims, self._private_key, algorithm="RS256", headers={"kid": self.kid})

    def decode_access_token(self, token: str) -> dict[str, Any]:
        """Verify + decode an access token; raises jwt.PyJWTError on any failure."""
        return jwt.decode(
            token,
            self._public_key,
            algorithms=["RS256"],
            issuer=self.issuer,
        )

    # ---- JWKS --------------------------------------------------------------
    def jwks(self) -> dict[str, Any]:
        public_numbers = self._public_key.public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": self.kid,
                    "use": "sig",
                    "alg": "RS256",
                    "n": _b64(
                        public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, "big")
                    ),
                    "e": _b64(
                        public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, "big")
                    ),
                }
            ]
        }


def _b64(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def build_jwt_mint_from_settings() -> JWTMint:
    settings = get_settings()
    return JWTMint(
        private_key_pem=os.environ.get("JWT_PRIVATE_KEY") or None,
        public_key_pem=os.environ.get("JWT_PUBLIC_KEY") or None,
        kid=settings.jwt_kid,
        issuer=settings.jwt_issuer,
        access_ttl_sec=settings.jwt_access_ttl_sec,
    )


__all__ = ["JWTMint", "build_jwt_mint_from_settings"]

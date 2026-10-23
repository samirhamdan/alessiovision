"""Segredos: senhas (Argon2id), tokens opacos e códigos de ativação.

Tokens e códigos de alta entropia são guardados só como SHA-256 (busca direta
pelo hash). Senhas, de baixa entropia, usam Argon2id.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
# Usado quando o e-mail não existe, para o tempo de resposta não revelar quais contas existem.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

MIN_PASSWORD_LENGTH = 10
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O e 1/I, fáceis de confundir


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_agent_token() -> str:
    return "alg_" + secrets.token_urlsafe(32)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


def generate_enrollment_code() -> str:
    """Código para digitar no agente: 4 grupos de 4 (80 bits), ex.: K7QX-M2PA-9TRD-H4WN."""
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(16))
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


def normalize_enrollment_code(code: str) -> str:
    raw = "".join(ch for ch in code.upper() if ch.isalnum())
    return "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres."
    if len(password) > 256:
        return "A senha pode ter no máximo 256 caracteres."
    return None

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ALESSIO_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://alessio:alessio@localhost:5432/alessio"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Desligue só em desenvolvimento por HTTP fora de localhost.
    cookie_secure: bool = True
    session_hours: int = 12
    invite_hours: int = 72
    enrollment_hours: int = 24
    # Teste grátis de serviço Vision por câmera (regra R2).
    trial_days: int = 3
    # Fim do serviço (regra R2, item 5): histórico só leitura por N dias, depois
    # oculto e apagado M dias depois (recuperável se renovar antes de apagar).
    history_grace_days: int = 30
    history_purge_days: int = 60
    max_failed_logins: int = 5
    lockout_minutes: int = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ALESSIO_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://alessio:alessio@localhost:5432/alessio"
    # Fase 0: o painel ainda não tem login e mostra apenas esta organização.
    # Substituído por autenticação de usuários na Fase 1.
    dashboard_org_id: UUID | None = None
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()

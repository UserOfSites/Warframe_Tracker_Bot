from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    discord_token: str = Field(..., alias="DISCORD_TOKEN")
    data_source: Literal["warframestat", "aggregate", "fake"] = Field(
        "warframestat", alias="DATA_SOURCE"
    )
    warframestat_base_url: str = Field("https://api.warframestat.us", alias="WARFRAMESTAT_BASE_URL")
    fissure_cache_ttl: int = Field(30, alias="FISSURE_CACHE_TTL")
    default_locale: str = Field("en", alias="DEFAULT_LOCALE")
    default_fast_missions: str = Field(
        "Exterminate,Sabotage,Capture,Rescue", alias="DEFAULT_FAST_MISSIONS"
    )
    default_dojoshare_nodes: str = Field(
        "Draco,Casta,Nimus,Mot,Ani,Elara,Io,Stephano,Circulus,Yuvarium",
        alias="DEFAULT_DOJOSHARE_NODES",
    )
    db_path: str = Field("./titania.db", alias="DB_PATH")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @field_validator("default_fast_missions", "default_dojoshare_nodes")
    @classmethod
    def _non_empty_csv(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be a non-empty comma-separated list")
        return v

    def fast_missions(self) -> frozenset[str]:
        return frozenset(s.strip() for s in self.default_fast_missions.split(",") if s.strip())

    def dojoshare_nodes(self) -> frozenset[str]:
        return frozenset(s.strip() for s in self.default_dojoshare_nodes.split(",") if s.strip())

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UNI_AGENT_", extra="ignore")

    model_name: str = Field(default="openai:gpt-4.1-mini")
    workspace: Path = Field(default_factory=lambda: Path(".").resolve())
    skills_dir: Path = Field(default_factory=lambda: Path("skills").resolve())
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()


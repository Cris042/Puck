from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    runs_dir: Path = Path("./runs")
    max_repair_cycles: int = 2

    # Prefix ATENA_BENCH_ is applied only to these benchmark settings.
    # Provider/LangSmith variables continue using their native environment names.


settings = Settings(_env_prefix="ATENA_BENCH_")

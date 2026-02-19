from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "KBETON ERP Bot"
    env: str = Field(default="dev", alias="ENV")
    tz: str = Field(default="Asia/Bishkek", alias="TZ")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(alias="DATABASE_URL")

    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    celery_broker_url: str = Field(default="redis://redis:6379/1", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://redis:6379/2", alias="CELERY_RESULT_BACKEND")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_default_chat_id: str = Field(default="", alias="TELEGRAM_DEFAULT_CHAT_ID")
    bot_fsm_storage: str = Field(default="memory", alias="BOT_FSM_STORAGE")
    bot_fsm_redis_url: str = Field(default="redis://redis:6379/3", alias="BOT_FSM_REDIS_URL")

    api_auth_enabled: bool = Field(default=False, alias="API_AUTH_ENABLED")
    api_token: str = Field(default="", alias="API_TOKEN")

    s3_endpoint_url: str = Field(default="http://minio:9000", alias="S3_ENDPOINT_URL")
    s3_access_key_id: str = Field(default="minioadmin", alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str = Field(default="minioadmin", alias="S3_SECRET_ACCESS_KEY")
    s3_bucket: str = Field(default="kbeton", alias="S3_BUCKET")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")

settings = Settings()

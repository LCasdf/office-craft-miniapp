from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    debug: bool = True

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "oc"
    mysql_password: str = "oc_dev_password"
    mysql_database: str = "office_craft"

    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = "redis://127.0.0.1:6379/1"
    celery_result_backend: str = "redis://127.0.0.1:6379/2"

    jwt_secret: str = "change-me"
    access_token_ttl_seconds: int = 7200
    refresh_token_ttl_seconds: int = 2592000

    max_inflight_tasks_per_user: int = 3
    upload_credential_ttl_seconds: int = 900
    download_url_ttl_seconds: int = 900
    input_ttl_seconds: int = 6 * 3600
    output_ttl_seconds: int = 24 * 3600
    cleanup_interval_seconds: int = 3600
    alert_interval_seconds: int = 300
    alert_success_rate_min: float = 0.95
    alert_queue_depth_max: int = 100
    alert_window_seconds: int = 900

    cos_secret_id: str = ""
    cos_secret_key: str = ""
    cos_region: str = "ap-guangzhou"
    cos_bucket: str = "office-craft"
    cos_env_prefix: str = "local"

    # MinIO / S3-compatible (local default). Empty endpoint → use AWS/COS style host later.
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region: str = "us-east-1"

    ai_provider: str = "mock"
    ai_api_key: str = ""
    ai_base_url: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

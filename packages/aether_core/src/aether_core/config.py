from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AetherSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AETHER_", extra="ignore")

    env: str = Field(default="development")
    cluster_name: str = Field(default="aether-local")
    log_level: str = Field(default="INFO")
    service_name: str = Field(default="aether-service")
    api_token: str = Field(default="change-me")

    redis_url: str = Field(default="redis://localhost:6379/0")
    kafka_bootstrap_servers: str = Field(default="localhost:9092")
    neo4j_uri: str = Field(default="neo4j://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="password")
    postgres_dsn: str = Field(default="postgresql://postgres:postgres@localhost:5432/aether")
    timescale_dsn: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/aether_metrics"
    )
    vault_addr: str = Field(default="http://localhost:8200")
    otel_exporter_otlp_endpoint: str = Field(default="http://localhost:4317")

    reasoning_trigger_threshold: float = Field(default=0.8)
    fusion_window_seconds: int = Field(default=5)
    temporal_alignment_tolerance_ms: int = Field(default=100)
    embedding_dimension: int = Field(default=768)
    event_bus_backend: str = Field(default="memory")
    event_bus_topic_prefix: str = Field(default="aether")
    event_bus_poll_interval_ms: int = Field(default=500)
    startup_retry_attempts: int = Field(default=20)
    startup_retry_delay_seconds: float = Field(default=1.0)
    ingestion_service_url: str = Field(default="http://localhost:8001")
    fusion_service_url: str = Field(default="http://localhost:8002")
    memory_service_url: str = Field(default="http://localhost:8003")
    reasoning_service_url: str = Field(default="http://localhost:8004")
    governance_service_url: str = Field(default="http://localhost:8005")
    action_service_url: str = Field(default="http://localhost:8006")
    realtime_service_url: str = Field(default="http://localhost:8007")
    kernel_service_url: str = Field(default="http://localhost:8008")


@lru_cache
def get_settings(service_name: str = "aether-service") -> AetherSettings:
    return AetherSettings(service_name=service_name)

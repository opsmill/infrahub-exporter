import os
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# --- Metrics Configuration ---
class MetricsKind(BaseModel):
    """Defines filter and parameters for a specific Infrahub Kind."""

    kind: str
    include: list[str] = Field(default_factory=list)
    filters: list[dict[str, str]] = Field(default_factory=list)


class MetricsConfig(BaseModel):
    """Configuration for metrics collection."""

    kind: list[MetricsKind] = Field(default_factory=list)


# --- Infrahub Configuration ---
class InfrahubConfig(BaseModel):
    """Configuration for Infrahub connection."""

    address: str = Field(
        default="http://localhost:8000", description="Infrahub API base URL"
    )
    token: str = Field(..., description="Bearer token for Infrahub authentication")
    branch: str = Field(default="main", description="Git branch or version to query")


# --- Exporters Configuration ---
class PrometheusConfig(BaseModel):
    """Configuration for Prometheus exporter."""

    enabled: bool = Field(
        default=False, description="Enable Prometheus metrics endpoint"
    )
    metrics_path: str = Field(
        default="/metrics", description="HTTP path for metrics exposure"
    )


class OTLPConfig(BaseModel):
    """Configuration for OTLP exporter."""

    enabled: bool = Field(
        default=False, description="Enable OpenTelemetry exporting via OTLP"
    )
    endpoint: str = Field(
        default="http://otel-collector:4317", description="OTLP collector endpoint URL"
    )
    timeout_seconds: int = Field(
        default=10, gt=0, description="Request timeout in seconds for OTLP exporter"
    )


class ExportersConfig(BaseModel):
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    otlp: OTLPConfig = Field(default_factory=OTLPConfig)


# --- Service Discovery Configuration ---
class ServiceDiscoveryQuery(BaseModel):
    """Configuration for a single service discovery GraphQL query."""

    file_path: str
    target_field: str
    refresh_interval_seconds: int = Field(default=60, gt=0)
    label_mappings: dict[str, str] = Field(default_factory=dict)
    port_field: str | None = None
    name: str | None = None

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.name: str | None = self.file_path.split("/")[-1].split(".")[0]


class ServiceDiscoveryConfig(BaseModel):
    """Configuration for Prometheus HTTP Service Discovery."""

    enabled: bool = Field(default=False)
    queries: list[ServiceDiscoveryQuery] = Field(default_factory=list)


# --- Sidecar Settings ---
class SidecarSettings(BaseSettings):
    """Main configuration for the sidecar service."""

    infrahub: InfrahubConfig
    exporters: ExportersConfig = Field(default_factory=ExportersConfig)
    service_discovery: ServiceDiscoveryConfig = Field(
        default_factory=ServiceDiscoveryConfig
    )
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    poll_interval_seconds: int = Field(default=60, gt=1)
    listen_address: str = Field(default="0.0.0.0")
    listen_port: int = Field(default=8001, gt=0)
    log_level: str = Field(default="INFO")

    class Config:
        env_prefix = "INFRAHUB_SIDECAR_"
        case_sensitive = False

    @classmethod
    def load(cls, path: str) -> "SidecarSettings":
        """Load configuration from a YAML file and validate with Pydantic."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r") as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict) or not raw:
            raise ValueError(f"Empty or invalid YAML in configuration file: {path}")

        # Instantiate and validate nested settings
        return cls(**raw)

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Infrahub Exporter is a Python microservice that bridges Infrahub (infrastructure management platform) with monitoring systems. It provides:
- Prometheus metrics export via `/metrics` endpoint
- Dynamic service discovery for Prometheus via `/sd/{query_name}` endpoints
- OpenTelemetry (OTLP) metrics export via gRPC

## Development Commands

```bash
# Install dependencies
poetry install --no-interaction

# Run the exporter
poetry run python infrahub_exporter/main.py --config config.yml

# Format code
invoke format

# Run all linters (yamllint, ruff, mypy)
invoke lint

# Run individual linters
invoke lint-ruff
invoke lint-mypy
invoke lint-yaml

# Build documentation
invoke docs  # requires npm install in docs/
```

## Architecture

The codebase follows an async event-driven pattern with four core modules:

- **main.py**: Entry point and FastAPI HTTP server (`Server` class). Orchestrates startup, registers routes, handles graceful shutdown.
- **config.py**: Pydantic models for YAML configuration. Root model is `SidecarSettings`. Supports env var overrides via `INFRAHUB_SIDECAR_*` prefix.
- **metrics_exporter.py**: `MetricsExporter` implements Prometheus `Collector` interface. Runs background polling loop, stores metrics in `_store` dict, exports to both Prometheus (scrape) and OTLP (push).
- **service_discovery.py**: `ServiceDiscoveryManager` executes GraphQL queries against Infrahub, transforms results to Prometheus SD JSON format with per-query TTL caching.

### Data Flow

1. YAML config loaded via `SidecarSettings.load(path)` with Pydantic validation
2. `InfrahubClient` (from infrahub-sdk) connects to Infrahub server
3. `MetricsExporter` polls Infrahub on configured interval, stores metrics
4. HTTP server exposes health (`/`), metrics (`/metrics`), and service discovery (`/sd/*`) endpoints

## Configuration

Configuration is YAML-based (see `examples/config.yml`). Key sections:
- `infrahub`: Server address, API token, branch
- `exporters`: Enable/configure Prometheus and OTLP exporters
- `service_discovery`: GraphQL queries for dynamic target discovery
- `metrics`: Node kinds to collect with optional filters

## Python Version

Targets Python 3.10-3.12 (see `pyproject.toml`).

## Type Checking

The project uses strict mypy settings with `disallow_untyped_defs = true`. All functions must have type annotations.

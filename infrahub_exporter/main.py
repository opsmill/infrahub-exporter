import argparse
import asyncio
import logging
import sys

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from infrahub_sdk import Config, InfrahubClient
from prometheus_client import REGISTRY, generate_latest

from .config import ServiceDiscoveryConfig, ServiceDiscoveryQuery, SidecarSettings
from .metrics_exporter import MetricsExporter
from .service_discovery import ServiceDiscoveryManager

# Setup root logger
logger = logging.getLogger("infrahub-sidecar")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(handler)


class Server:
    """HTTP server for health, metrics, and service-discovery endpoints."""

    def __init__(
        self,
        sd_config: ServiceDiscoveryConfig | None,
        client: InfrahubClient,
        listen_address: str,
        listen_port: int,
    ):
        self.sd_config = sd_config
        self.client = client
        self.listen_address = listen_address
        self.listen_port = listen_port
        self.app = FastAPI(title="Infrahub Sidecar")
        self.sd_manager = (
            ServiceDiscoveryManager(client) if sd_config and sd_config.enabled else None
        )
        self._setup_routes()

    def _setup_routes(self) -> JSONResponse | None:
        @self.app.get("/")
        async def health() -> PlainTextResponse:
            return PlainTextResponse("OK")

        @self.app.get("/metrics")
        async def metrics() -> Response:
            data = generate_latest(REGISTRY)
            return Response(
                content=data,
                media_type="text/plain; version=0.0.4",
            )

        logger.info("Registered metrics endpoint: /metrics")

        if self.sd_manager and self.sd_config and self.sd_config.queries:
            for query in self.sd_config.queries:
                path = f"/sd/{query.name}"

                @self.app.get(path)
                async def sd_endpoint(
                    req: Request, q: ServiceDiscoveryQuery = query
                ) -> JSONResponse:
                    return await self._handle_sd(q)

                logger.info(f"Registered SD endpoint: {path}")
        return None

    async def _handle_sd(self, query: ServiceDiscoveryQuery) -> JSONResponse:
        if self.sd_manager:
            try:
                targets = await self.sd_manager.get_targets(query)
                resp = JSONResponse(content=targets)
                resp.headers["X-Prometheus-Refresh-Interval-Seconds"] = str(
                    query.refresh_interval_seconds
                )
                return resp
            except Exception as e:
                logger.error(f"SD '{query.name}' error: {e}")
                return JSONResponse(content=[], status_code=500)

        return JSONResponse(content=[], status_code=404)

    async def start(self) -> None:
        config = uvicorn.Config(
            app=self.app,
            host=self.listen_address,
            port=self.listen_port,
            log_level=logging.getLevelName(logger.level).lower(),
        )
        server = uvicorn.Server(config)
        asyncio.create_task(server.serve())
        logger.info(f"Server listening on {self.listen_address}:{self.listen_port}")

    async def stop(self) -> None:
        logger.info("Stopping server...")
        await asyncio.sleep(0.1)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Infrahub Sidecar Service")
    parser.add_argument(
        "-c", "--config", default="config.yml", help="Path to YAML config file"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override logging level",
    )
    args = parser.parse_args()

    try:
        cfg = SidecarSettings.load(args.config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    if args.log_level:
        logger.setLevel(args.log_level)
    else:
        logger.setLevel(cfg.log_level)
    logger.info(f"Config loaded from {args.config}")

    client = InfrahubClient(
        address=cfg.infrahub.address,
        config=Config(
            api_token=cfg.infrahub.token,
            default_branch=cfg.infrahub.branch,
            tls_insecure=False,
            timeout=10,
        ),
    )

    # Start metrics exporter
    metrics_exporter = MetricsExporter(client=client, settings=cfg)
    await metrics_exporter.start()

    # Start HTTP server for metrics & service discovery
    server = Server(
        sd_config=cfg.service_discovery,
        client=client,
        listen_address=cfg.listen_address,
        listen_port=cfg.listen_port,
    )
    await server.start()

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received")
    finally:
        await metrics_exporter.stop()
        await server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

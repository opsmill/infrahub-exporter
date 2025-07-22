import asyncio
import logging
from typing import Any, Generator

from prometheus_client.core import GaugeMetricFamily, REGISTRY
from prometheus_client.registry import Collector
from opentelemetry import metrics as otel_metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from infrahub_sdk import InfrahubClient
from infrahub_sdk.exceptions import SchemaNotFoundError
from infrahub_sdk.node.node import InfrahubNode
from infrahub_sdk.node.relationship import RelationshipManager
from infrahub_sdk.protocols_base import RelatedNode

from .config import MetricsKind, SidecarSettings

logger = logging.getLogger(name="infrahub-sidecar")


class MetricEntry:
    """Represents a single metric data point with labels and value."""

    def __init__(self, labels: dict[str, Any], value: int) -> None:
        self.labels = labels
        self.value = value


class MetricsExporter(Collector):
    """Unified metrics exporter for Prometheus and OTLP based on configured kinds."""

    class MetricMeter:
        def __init__(self, kp: MetricsKind, exporter: "MetricsExporter"):
            self.kp = kp
            self.exporter = exporter

        def _otlp_callback(
            self, options: Any | None
        ) -> Generator[Observation, None, None]:
            """Callback to emit current OTLP metrics."""
            labels = ["id", "hfid"] + self.kp.include
            for entry in self.exporter._store[self.kp.kind]:
                yield Observation(
                    value=entry.value,
                    attributes={label: entry.labels.get(label, "") for label in labels},
                )

    def __init__(self, client: InfrahubClient, settings: SidecarSettings):
        self.client = client
        self.settings = settings
        self._store: dict[str, list[MetricEntry]] = {}
        self._poll_task: asyncio.Task | None = None

    def register_prometheus(self) -> None:
        """Register this instance as a Prometheus collector."""
        REGISTRY.register(self)
        logger.info("Prometheus metrics collector registered")

    async def start_otlp(self) -> None:
        """Setup OTLP meter provider and observable gauges for each kind."""
        otlp_cfg = self.settings.exporters.otlp
        exporter = OTLPMetricExporter(
            endpoint=otlp_cfg.endpoint,
            timeout=otlp_cfg.timeout_seconds,
        )
        reader = PeriodicExportingMetricReader(exporter)
        provider = MeterProvider(metric_readers=[reader])
        otel_metrics.set_meter_provider(provider)
        meter = otel_metrics.get_meter(__name__)

        for kp in self.settings.metrics.kind:
            metric_name = f"infrahub_{kp.kind.lower()}_info"
            metric_meter = self.MetricMeter(kp=kp, exporter=self)

            meter.create_observable_gauge(
                name=metric_name,
                description=f"Info about Infrahub {kp.kind}",
                callbacks=[metric_meter._otlp_callback],
            )
        logger.info("OTLP observable gauges created")

    def collect(self) -> Generator[GaugeMetricFamily, None, None]:
        """Prometheus collect method: yield metrics from store."""
        for kind, entries in self._store.items():
            # Find the corresponding MetricsKind config
            kp = next((k for k in self.settings.metrics.kind if k.kind == kind), None)
            if not kp:
                continue
            metric_name = f"infrahub_{kind.lower()}_info"
            labels = ["id", "hfid"] + kp.include
            metric = GaugeMetricFamily(
                metric_name,
                f"Info about Infrahub {kind}",
                labels=labels,
            )
            for entry in entries:
                metric.add_metric(
                    [entry.labels.get(label, "") for label in labels],
                    entry.value,
                )
            yield metric

    async def _fetch_and_store(self, kp: Any) -> None:
        """Fetch items for one kind and store MetricEntry list."""
        try:
            items: list[InfrahubNode] = []
            logger.debug(f"Fetching items for kind '{kp.kind}'")
            filter_args: dict[str, Any] = {}
            for f in kp.filters:
                filter_args.update(f)

            if filter_args:
                items = await self.client.filters(
                    kind=kp.kind,
                    include=kp.include,
                    branch=self.settings.infrahub.branch,
                    **filter_args,
                )
            else:
                items = await self.client.all(
                    kind=kp.kind,
                    include=kp.include,
                    branch=self.settings.infrahub.branch,
                )
            logger.debug(f"Fetched {len(items)} items for kind '{kp.kind}'")

        except SchemaNotFoundError:
            logger.error(f"Schema not found for kind '{kp.kind}'")
        except Exception as exc:
            logger.error(f"Error fetching items for kind '{kp.kind}': {exc}")

        entries: list[MetricEntry] = []
        for itm in items:
            labels: dict[str, Any] = {
                "id": str(itm.id or ""),
                "hfid": itm.get_human_friendly_id_as_string(include_kind=True) or "",
            }
            # Handle attributes & relationships
            for field in kp.include:
                val = None
                attr = getattr(itm, field, None)
                if attr is None:
                    labels[field] = ""
                    continue
                # Relationship (single)
                if isinstance(attr, RelatedNode):
                    if attr.initialized:
                        await attr.fetch()
                        peer = itm._client.store.get(
                            key=attr.peer.id, raise_when_missing=False
                        )
                        if peer:
                            val = (
                                peer.get_human_friendly_id_as_string(include_kind=True)
                                or peer.id
                            )
                # Relationship (multiple)
                elif isinstance(attr, RelationshipManager):
                    if attr.initialized:
                        peers = []
                        for p in attr.peers:
                            node = itm._client.store.get(
                                key=p.id, raise_when_missing=False
                            )
                            if not node:
                                await p.fetch()
                                node = p.peer
                            peers.append(
                                node.get_human_friendly_id_as_string(include_kind=True)
                                or node.id
                            )
                        val = ",".join(peers)
                # Attribute
                else:
                    val = getattr(attr, "value", None)
                labels[field] = str(val or "")

            entries.append(MetricEntry(labels=labels, value=1))

        self._store[kp.kind] = entries

    async def _poll_loop(self) -> None:
        """Background loop to fetch metrics periodically."""
        interval = self.settings.poll_interval_seconds
        while True:
            tasks = [self._fetch_and_store(kp) for kp in self.settings.metrics.kind]
            await asyncio.gather(*tasks)
            await asyncio.sleep(interval)

    async def start(self) -> None:
        """Initialize exporters and start polling loop."""
        if self.settings.exporters.prometheus.enabled:
            self.register_prometheus()
        if self.settings.exporters.otlp.enabled:
            await self.start_otlp()
        # Kick off background fetching
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Started background polling for metrics")

    async def stop(self) -> None:
        """Cancel background tasks if running."""
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped background polling for metrics")

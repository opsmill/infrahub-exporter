import time
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from infrahub_sdk import InfrahubClient

from .config import ServiceDiscoveryQuery

logger = logging.getLogger(name="infrahub-sidecar")


class CachedTargets(BaseModel):
    """Cache entry holding timestamp and list of target groups."""

    timestamp: float
    targets: list[dict[str, Any]]


class ServiceDiscoveryManager:
    """Handles GraphQL queries for Prometheus service discovery with per-query TTL caching."""

    def __init__(self, client: InfrahubClient):
        self.client = client
        self._cache: dict[str, CachedTargets] = {}

    async def get_targets(self, query: ServiceDiscoveryQuery) -> list[dict[str, Any]]:
        """Return cached targets or fetch fresh if TTL expired."""
        now = time.monotonic()
        targets = []
        if query.name:
            cached = self._cache.get(query.name)

            if cached and (now - cached.timestamp) < query.refresh_interval_seconds:
                logger.debug(f"Returning cached SD for '{query.name}'")
                return cached.targets

            targets = await self._fetch_and_transform(query)
            self._cache[query.name] = CachedTargets(timestamp=now, targets=targets)
        return targets

    async def _fetch_and_transform(
        self, query: ServiceDiscoveryQuery
    ) -> list[dict[str, Any]]:
        """Load GQL file, execute, and format response for Prometheus."""
        path = Path(query.file_path)
        if not path.is_absolute():
            path = Path.cwd() / query.file_path

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Cannot read query file {path}: {e}")
            return []

        try:
            resp = await self.client.execute_graphql(
                query=content,
                raise_for_error=False,
            )
        except Exception as e:
            logger.error(f"GraphQL execution failed for '{query.name}': {e}")
            return []

        if "errors" in resp:
            logger.error(f"GraphQL errors in '{query.name}': {resp['errors']}")
            return []

        raw = resp.get("data", resp)
        targets: list[dict[str, Any]] = []
        for kind_name, data_block in raw.items():
            edges = data_block.get("edges") if isinstance(data_block, dict) else None
            if not isinstance(edges, list):
                continue

            for edge in edges:
                node = edge.get("node", {})
                addr = self._extract_field(node, query.target_field)
                if not addr:
                    continue
                if query.port_field:
                    port = self._extract_field(node, query.port_field)
                    if port:
                        addr = f"{addr}:{port}"

                labels: dict[str, Any] = {}
                for key, field_path in query.label_mappings.items():
                    val = self._extract_field(node, field_path)
                    if val is not None:
                        label_key = key
                        labels[label_key] = str(val)

                labels["__meta_infrahub_id"] = node.get("id")
                labels["__meta_infrahub_kind"] = kind_name
                targets.append({"targets": [addr], "labels": labels})

        logger.info(f"SD '{query.name}' generated {len(targets)} targets")
        return targets

    def _extract_field(self, node: dict[str, Any], path_expr: str) -> Any:
        """Extract nested field via dot-notation; handles arrays and GraphQL edges."""
        parts = path_expr.split(".")
        current: Any = node

        for part in parts:
            # Handle arrays with [] notation
            if part.endswith("[]"):
                arr_field = part[:-2]
                arr = current.get(arr_field)
                values: list[str] = []
                if isinstance(arr, dict) and "edges" in arr:
                    for entry in arr["edges"]:
                        txt = entry.get("node", {}).get("name", {}).get("value")
                        if txt is not None:
                            values.append(str(txt))
                elif isinstance(arr, list):
                    for item in arr:
                        if isinstance(item, (str, int, float, bool)):
                            values.append(str(item))
                        elif isinstance(item, dict) and "value" in item:
                            values.append(str(item["value"]))
                return ",".join(values) if values else None

            # Standard nested access or GraphQL node unwrapping
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif (
                isinstance(current, dict)
                and "node" in current
                and part in current["node"]
            ):
                current = current["node"][part]
            else:
                return None

            if current is None:
                return None

        # Final extraction
        if isinstance(current, dict):
            return str(current.get("value", "")) if "value" in current else None
        if isinstance(current, (str, int, float, bool)):
            return str(current)
        return None

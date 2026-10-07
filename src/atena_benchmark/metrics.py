from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import TypeVar

from langchain_core.callbacks import UsageMetadataCallbackHandler

from .config import PricingConfig
from .costing import calculate_usage_cost, resolve_price
from .schemas import InvocationMetric, TokenUsage

T = TypeVar("T")


class MetricsRecorder:
    def __init__(self, output_file: Path, pricing: PricingConfig):
        self.output_file = output_file
        self.pricing = pricing
        self.invocations: list[InvocationMetric] = []
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        # Arquivo sempre existe: vazio significa "nenhuma chamada", não "artefato perdido".
        self.output_file.touch()

    @staticmethod
    def _normalize_usage(model: str, raw: dict) -> TokenUsage:
        input_details = raw.get("input_token_details") or {}
        output_details = raw.get("output_token_details") or {}
        return TokenUsage(
            model=model,
            input_tokens=int(raw.get("input_tokens", 0) or 0),
            output_tokens=int(raw.get("output_tokens", 0) or 0),
            total_tokens=int(raw.get("total_tokens", 0) or 0),
            cache_read_tokens=int(input_details.get("cache_read", 0) or 0),
            cache_write_tokens=int(
                input_details.get("cache_creation", input_details.get("cache_write", 0)) or 0
            ),
            reasoning_tokens=int(output_details.get("reasoning", 0) or 0),
        )

    def of_kind(self, kind: str) -> list[InvocationMetric]:
        return [m for m in self.invocations if m.kind == kind]

    def unpriced_models(self) -> list[str]:
        return sorted(
            {u.model for m in self.invocations for u in m.usages if not u.priced_as}
        )

    def measured_invoke(
        self,
        *,
        role: str,
        run_name: str,
        tags: list[str],
        metadata: dict,
        invoke: Callable[..., T],
        payload: dict,
        configured_model: str = "",
        task_id: str = "",
        recursion_limit: int | None = None,
        kind: str = "execution",
    ) -> T:
        callback = UsageMetadataCallbackHandler()
        config = {
            "callbacks": [callback],
            "run_name": run_name,
            "tags": tags,
            "metadata": metadata,
        }
        if recursion_limit is not None:
            config["recursion_limit"] = recursion_limit
        # Timestamp absoluto: latência de API varia com a carga do provider (protocolo, 4.1).
        started_at = datetime.now(UTC).isoformat()
        start = perf_counter()
        error = ""
        try:
            return invoke(payload, config=config)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:2000]
            raise
        finally:
            # Tokens gastos antes de uma falha também custam: registra sempre.
            duration_ms = (perf_counter() - start) * 1000
            usages = []
            for model, raw in callback.usage_metadata.items():
                usage = self._normalize_usage(model, raw)
                resolved = resolve_price(model, self.pricing, configured_model)
                usage.priced_as = resolved[0] if resolved else ""
                usages.append(usage)
            cost = sum(
                calculate_usage_cost(u, self.pricing, configured_model) for u in usages
            )
            metric = InvocationMetric(
                role=role,
                kind=kind,
                model=configured_model,
                started_at=started_at,
                duration_ms=duration_ms,
                task_id=task_id,
                usages=usages,
                estimated_cost_usd=cost,
                error=error,
            )
            self.invocations.append(metric)
            with self.output_file.open("a", encoding="utf-8") as f:
                f.write(metric.model_dump_json() + "\n")

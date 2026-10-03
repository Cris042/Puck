from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .analysis import aggregate, run_row, to_csv, to_markdown
from .config import Strategy, load_models, load_pricing, pricing_problems
from .runner import run_experiment

app = typer.Typer(
    no_args_is_help=True,
    help="Benchmark de estratégias de LLM para engenharia de software.",
)
console = Console()


@app.command()
def run(
    experiment: Annotated[Path, typer.Option("--experiment", "-e")] = Path(
        "examples/atena/experiment.yaml"
    ),
    provider: Annotated[str, typer.Option("--provider", "-p")] = "openai",
    strategy: Annotated[Strategy, typer.Option("--strategy", "-s")] = "hierarchical",
    models: Annotated[Path, typer.Option("--models")] = Path("config/models.yaml"),
    pricing: Annotated[Path, typer.Option("--pricing")] = Path("config/pricing.yaml"),
    prompts: Annotated[Path, typer.Option("--prompts")] = Path("prompts"),
    runs_dir: Annotated[Path | None, typer.Option("--runs-dir")] = None,
    allow_unpriced: Annotated[
        bool, typer.Option(help="Executa mesmo com modelos sem preço (custo sairá zerado).")
    ] = False,
):
    """Executa um benchmark completo em uma cópia isolada do repositório alvo."""
    problems = pricing_problems(load_models(models), load_pricing(pricing))
    if problems and not allow_unpriced:
        for problem in problems:
            console.print(f"[red]✗[/red] {problem}")
        console.print("Corrija o pricing.yaml ou use --allow-unpriced.")
        raise typer.Exit(1)

    summary, run_dir = run_experiment(
        experiment_file=experiment,
        models_file=models,
        pricing_file=pricing,
        provider=provider,
        strategy=strategy,
        prompts_dir=prompts,
        runs_dir=runs_dir,
    )

    table = Table(title="Resultado do benchmark")
    table.add_column("Métrica")
    table.add_column("Valor", justify="right")
    table.add_row("Run ID", summary.run_id)
    table.add_row("Provider", summary.provider)
    table.add_row("Estratégia", summary.strategy)
    table.add_row("Governança", summary.governance)
    table.add_row("Commit base", summary.base_commit[:12])
    table.add_row("Tokens", f"{summary.total_tokens:,}")
    table.add_row("Custo estimado", f"US$ {summary.total_cost_usd:.4f}")
    table.add_row("Tarefas", f"{summary.tasks_completed}/{summary.tasks_total} ({summary.task_source})")
    table.add_row("Ciclos de correção", str(summary.repair_cycles))
    table.add_row(
        "Revisão final",
        "APROVADO" if summary.final_review and summary.final_review.approved else "PENDÊNCIAS",
    )
    table.add_row("Erros", str(len(summary.errors)))
    table.add_row("Execução válida", "sim" if summary.valid else "NÃO (repita)")
    console.print(table)
    if summary.unpriced_models:
        console.print(f"[yellow]Modelos sem preço: {', '.join(summary.unpriced_models)}[/yellow]")
    console.print(f"Artefatos: [bold]{run_dir / 'artifacts'}[/bold]")


@app.command("validate-config")
def validate_config(
    models: Annotated[Path, typer.Option("--models")] = Path("config/models.yaml"),
    pricing: Annotated[Path, typer.Option("--pricing")] = Path("config/pricing.yaml"),
    ping: Annotated[
        bool,
        typer.Option(
            help="Faz uma chamada mínima a cada modelo para validar ID, chave e parâmetros."
        ),
    ] = False,
):
    """Valida configuração de modelos e preços. Sem --ping, não chama nenhuma LLM."""
    model_cfg = load_models(models)
    pricing_cfg = load_pricing(pricing)
    configured = {
        provider: {
            "strong": cfg.strong.model,
            "medium": cfg.medium.model,
            "weak": cfg.weak.model,
        }
        for provider, cfg in model_cfg.providers.items()
    }
    problems = pricing_problems(model_cfg, pricing_cfg)
    console.print_json(
        json.dumps(
            {
                "models": configured,
                "judge": model_cfg.judge.model_dump() if model_cfg.judge else None,
                "pricing_date": pricing_cfg.pricing_date,
                "priced_models": sorted(pricing_cfg.models),
                "problems": problems,
            }
        )
    )
    failed = bool(problems)

    if ping:
        from .models import ModelRegistry

        for provider in model_cfg.providers:
            registry = ModelRegistry(model_cfg, provider=provider, strategy="hierarchical")
            for role in ("architect", "planner", "implementer"):
                tier, spec, model = registry.for_role(role)
                try:
                    model.invoke("Responda apenas: OK")
                    console.print(f"[green]✓[/green] {provider}/{tier}: {spec.model}")
                except Exception as exc:
                    failed = True
                    console.print(f"[red]✗[/red] {provider}/{tier}: {spec.model} — {exc}")

    if failed:
        raise typer.Exit(1)


@app.command()
def evaluate(
    run_dirs: Annotated[list[Path], typer.Argument(help="Diretórios runs/<run-id>.")],
    models: Annotated[Path, typer.Option("--models")] = Path("config/models.yaml"),
    pricing: Annotated[Path, typer.Option("--pricing")] = Path("config/pricing.yaml"),
    force: Annotated[bool, typer.Option(help="Reavalia execuções já avaliadas.")] = False,
):
    """Avalia execuções com o juiz fixo de models.yaml (cego a provider/estratégia)."""
    from .evaluation import evaluate_run

    model_cfg = load_models(models)
    if model_cfg.judge is None:
        console.print("[red]Configure `judge:` em models.yaml.[/red]")
        raise typer.Exit(1)
    pricing_cfg = load_pricing(pricing)
    for run_dir in run_dirs:
        if (run_dir / "artifacts" / "evaluation.json").exists() and not force:
            console.print(f"[dim]já avaliado: {run_dir.name}[/dim]")
            continue
        result = evaluate_run(run_dir, model_cfg.judge, pricing_cfg)
        scores = ", ".join(
            f"{d}={getattr(result, d).score}"
            for d in ("requirements", "regressions", "architecture", "security", "simplicity", "tests")
        )
        console.print(f"[green]✓[/green] {run_dir.name}: {scores}")


@app.command()
def compare(
    run_dirs: Annotated[list[Path], typer.Argument(help="Diretórios runs/<run-id>.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Prefixo para gravar .md e .csv.")
    ] = None,
):
    """Agrega repetições por provider × estratégia × governança (média ± desvio padrão)."""
    rows = [row for d in run_dirs if (row := run_row(d)) is not None]
    groups = aggregate(rows)
    markdown = to_markdown(groups)
    console.print(markdown)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix(".md").write_text(markdown, encoding="utf-8")
        output.with_suffix(".runs.csv").write_text(to_csv(rows), encoding="utf-8")
        output.with_suffix(".groups.csv").write_text(to_csv(groups), encoding="utf-8")
        console.print(f"Gravado em {output.with_suffix('.md')} e CSVs.")


if __name__ == "__main__":
    app()

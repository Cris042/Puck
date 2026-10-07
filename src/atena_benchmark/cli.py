from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from .analysis import aggregate, run_row, to_csv, to_markdown
from .config import Methodology, load_models, load_pricing, pricing_problems
from .runner import run_experiment

app = typer.Typer(
    no_args_is_help=True,
    help="Puck: benchmark de metodologias de desenvolvimento assistido por LLM.",
)
console = Console()


@app.command()
def run(
    experiment: Annotated[Path, typer.Option("--experiment", "-e")],
    methodology: Annotated[Methodology, typer.Option("--methodology", "-m")],
    models: Annotated[Path, typer.Option("--models")] = Path("config/models.yaml"),
    pricing: Annotated[Path, typer.Option("--pricing")] = Path("config/pricing.yaml"),
    prompts: Annotated[Path, typer.Option("--prompts")] = Path("prompts"),
    runs_dir: Annotated[Path | None, typer.Option("--runs-dir")] = None,
    allow_unpriced: Annotated[
        bool, typer.Option(help="Executa mesmo com modelos sem preço (custo sairá zerado).")
    ] = False,
):
    """Executa uma célula (tech do experimento × metodologia) num workspace novo."""
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
        methodology=methodology,
        prompts_dir=prompts,
        runs_dir=runs_dir,
    )

    table = Table(title="Resultado da execução")
    table.add_column("Métrica")
    table.add_column("Valor", justify="right")
    table.add_row("Run ID", summary.run_id)
    table.add_row("Tech", summary.tech)
    table.add_row("Metodologia", summary.methodology)
    for name, sha in summary.source_shas.items():
        table.add_row(f"SHA {name}", sha[:12])
    table.add_row("Tokens de execução", f"{summary.total_tokens:,}")
    table.add_row("Custo de execução", f"US$ {summary.total_cost_usd:.4f}")
    table.add_row("Custo de telemetria", f"US$ {summary.telemetry_cost_usd:.4f}")
    table.add_row(
        "Telemetria (falhas de parse)",
        f"{summary.telemetry_parse_failures}/{summary.telemetry_records}",
    )
    if summary.methodology == "m2":
        table.add_row("Tarefas aprovadas", f"{summary.tasks_completed}/{summary.tasks_total}")
        table.add_row("Ciclos de reparo", str(summary.repair_cycles))
    table.add_row("Erros", str(len(summary.errors)))
    table.add_row("Execução válida", "sim" if summary.valid else "NÃO (repita)")
    console.print(table)
    if summary.unpriced_models:
        console.print(f"[yellow]Modelos sem preço: {', '.join(summary.unpriced_models)}[/yellow]")
    console.print(f"Artefatos: [bold]{run_dir / 'artifacts'}[/bold]")


class _Ping(BaseModel):
    ok: bool


@app.command("validate-config")
def validate_config(
    models: Annotated[Path, typer.Option("--models")] = Path("config/models.yaml"),
    pricing: Annotated[Path, typer.Option("--pricing")] = Path("config/pricing.yaml"),
    ping: Annotated[
        bool,
        typer.Option(
            help="Chama cada modelo (texto + saída estruturada) para validar ID, chave e parâmetros."
        ),
    ] = False,
):
    """Valida configuração de modelos e preços. Sem --ping, não chama nenhuma LLM."""
    model_cfg = load_models(models)
    pricing_cfg = load_pricing(pricing)
    problems = pricing_problems(model_cfg, pricing_cfg)
    roles = {"m1.agent": model_cfg.m1.agent}
    roles |= {f"m2.{role}": spec for role, spec in model_cfg.m2}
    roles["telemetry"] = model_cfg.telemetry
    console.print_json(
        json.dumps(
            {
                "roles": {name: spec.generation_params() for name, spec in roles.items()},
                "judges": [j.model_dump(exclude={"extra"}) for j in model_cfg.judges],
                "pricing_date": pricing_cfg.pricing_date,
                "problems": problems,
            }
        )
    )
    failed = bool(problems)

    if ping:
        from .models import build_chat_model

        targets = [(name, spec, model_cfg.provider) for name, spec in roles.items()]
        targets += [(f"judge.{j.name}", j, j.provider) for j in model_cfg.judges]
        for name, spec, provider in targets:
            model = build_chat_model(spec, provider)
            method = "json_schema" if provider == "anthropic" else "function_calling"
            try:
                model.invoke("Responda apenas: OK")
                model.with_structured_output(_Ping, method=method).invoke("Responda ok=true.")
                console.print(f"[green]✓[/green] {name}: {spec.model}")
            except Exception as exc:
                failed = True
                console.print(f"[red]✗[/red] {name}: {spec.model} — {exc}")

    if failed:
        raise typer.Exit(1)


@app.command()
def evaluate(
    run_dirs: Annotated[list[Path], typer.Argument(help="Diretórios runs/<run-id>.")],
    models: Annotated[Path, typer.Option("--models")] = Path("config/models.yaml"),
    pricing: Annotated[Path, typer.Option("--pricing")] = Path("config/pricing.yaml"),
    prompts: Annotated[Path, typer.Option("--prompts")] = Path("prompts"),
    judge: Annotated[
        list[str] | None, typer.Option("--judge", help="Nome do juiz; repetível. Padrão: todos.")
    ] = None,
    force: Annotated[bool, typer.Option(help="Reavalia execuções já avaliadas.")] = False,
):
    """Avalia execuções com os juízes fixos de models.yaml (cegos à metodologia)."""
    from .evaluation import evaluate_run

    model_cfg = load_models(models)
    judges = [j for j in model_cfg.judges if not judge or j.name in judge]
    if not judges:
        console.print("[red]Nenhum juiz configurado/selecionado em `judges:`.[/red]")
        raise typer.Exit(1)
    pricing_cfg = load_pricing(pricing)
    for run_dir in run_dirs:
        for spec in judges:
            target = run_dir / "artifacts" / "evaluations" / f"{spec.name}.json"
            if target.exists() and not force:
                console.print(f"[dim]já avaliado: {run_dir.name} / {spec.name}[/dim]")
                continue
            result = evaluate_run(run_dir, spec, pricing_cfg, prompts)
            scores = ", ".join(
                f"{d}={getattr(result, d).score}"
                for d in ("requirements", "regressions", "architecture", "security", "simplicity",
                          "tests")
            )
            console.print(f"[green]✓[/green] {run_dir.name} / {spec.name}: {scores}")


sandbox_app = typer.Typer(help="Execução isolada do código gerado (usado pelos checks).")
app.add_typer(sandbox_app, name="sandbox")


@sandbox_app.command("check")
def sandbox_check(
    tech: Annotated[str, typer.Option("--tech")],
    target: Annotated[str, typer.Option("--target", help="Alvo de make da base técnica.")],
    repo: Annotated[Path, typer.Option("--repo")],
):
    """Roda `make <target>` do projeto no sandbox; o exit code é o do make."""
    from .sandbox import run_make_target

    raise typer.Exit(run_make_target(tech, target, repo))


@sandbox_app.command("build-images")
def sandbox_build_images():
    """Constrói as imagens de checks do harness que ainda não existirem."""
    from .sandbox import ensure_images

    built = ensure_images(Path(__file__).resolve().parents[2])
    console.print(f"Construídas: {', '.join(built) or 'nenhuma (já existiam)'}")


@app.command()
def compare(
    run_dirs: Annotated[list[Path], typer.Argument(help="Diretórios runs/<run-id>.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Prefixo para gravar .md e .csv.")
    ] = None,
):
    """Agrega repetições por tech × metodologia: mediana e pontos brutos."""
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

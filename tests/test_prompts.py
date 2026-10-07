from pathlib import Path

import pytest

from atena_benchmark.evaluation import build_judge_prompt, filter_patch
from atena_benchmark.prompts import PromptStore, render
from atena_benchmark.schemas import TelemetryReport

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"
SECTIONS = ("PAPEL", "OBJETIVO", "CONTEXTO", "TAREFA", "CRITÉRIOS", "RESTRIÇÕES", "FORMATO",
            "CONFIABILIDADE")


@pytest.mark.parametrize(
    "path", sorted(p for p in PROMPTS.rglob("*.md")), ids=lambda p: p.relative_to(PROMPTS).as_posix()
)
def test_every_prompt_follows_the_frozen_structure(path: Path):
    text = PromptStore(PROMPTS).load(path.relative_to(PROMPTS).with_suffix("").as_posix())
    headings = [line[2:].strip() for line in text.splitlines() if line.startswith("# ")]
    assert headings == list(SECTIONS)


def test_governance_reaches_only_m2():
    store = PromptStore(PROMPTS, governance="REGRA-DE-GOVERNANCA")
    assert "REGRA-DE-GOVERNANCA" not in store.system_prompt("m1", "implementer")
    assert "REGRA-DE-GOVERNANCA" in store.system_prompt("m2", "implementer")


def test_m1_prompt_has_no_governance_vocabulary():
    text = PromptStore(PROMPTS).system_prompt("m1", "agent").lower()
    for word in ("overengineering", "adr", "revisor", "gate", "minerva"):
        assert word not in text


def test_render_replaces_only_known_placeholders():
    text = render("<!-- {tech} -->{tech} usa {x} e {\"json\": 1}", {"tech": "Go"})
    assert text == "Go usa {x} e {\"json\": 1}"


def test_telemetry_rejects_regressions_without_executed_tests():
    report = TelemetryReport(declared_status="success", possible_regressions=["quebra login"])
    assert report.possible_regressions == []
    assert report.possible_regressions_rejected
    kept = TelemetryReport(
        declared_status="success", possible_regressions=["x"], tests_executed=["test"]
    )
    assert kept.possible_regressions == ["x"]


def test_judge_patch_hides_process_documents():
    patch = (
        "diff --git a/docs/adrs/adr-1.md b/docs/adrs/adr-1.md\n+M2 decidiu\n"
        "diff --git a/app/Nota.php b/app/Nota.php\n+class Nota {}\n"
    )
    filtered = filter_patch(patch)
    assert "adr-1" not in filtered and "class Nota" in filtered
    prompt = build_judge_prompt(
        brief="REQ", patch=patch, visible_baseline=[], visible_final=[],
        hidden_baseline=[], hidden_final=[],
    )
    for leaked in ("m1", "m2", "governada", "metodologia", "M2 decidiu"):
        assert leaked not in prompt

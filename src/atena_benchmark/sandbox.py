"""Execução isolada do código gerado pelas LLMs (checks, aplicação, oráculo, carga, DAST).

Duas etapas, nunca misturadas:

1. **Dependências** (`composer install --no-scripts --no-plugins` / `go mod download`): com rede,
   sem executar código do projeto. Resultado em volume Docker chaveado pelo hash do lockfile.
2. **Execução** (`make <alvo>`, aplicação): sem rede externa. Quando precisa de banco, roda numa
   rede Docker `--internal` com um PostgreSQL efêmero. O workspace entra somente-leitura e é
   copiado para dentro do container.

As imagens são do harness (`docker/checks/<tech>`); o Dockerfile/compose do projeto, escrito pela
LLM, nunca define o sandbox.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

POSTGRES_IMAGE = "postgres:18"
ORACLE_IMAGE = "puck-oracle"
ROOT = Path(__file__).resolve().parents[2]
APP_PORT = 8080
DB_TARGETS = {"test", "coverage", "migrate", "seed"}
# Camadas cuja cobertura a base técnica exige ≥ 90% (seção 6).
CORE_LAYER_MARKERS = ("/Dominio/", "/Service/", "/dominio/", "/service/")


@dataclass(frozen=True)
class TechSpec:
    image: str
    deps_files: tuple[str, ...]
    deps_command: str
    restore_command: str
    env: dict[str, str] = field(default_factory=dict)


TECHS: dict[str, TechSpec] = {
    "laravel": TechSpec(
        image="puck-checks-laravel",
        deps_files=("composer.json", "composer.lock"),
        deps_command=(
            "composer install --no-scripts --no-plugins --no-progress --prefer-dist"
            " && rm -rf /deps/vendor && mv vendor /deps/vendor"
        ),
        # Autoload regenerado offline, agora com os scripts do projeto (já sem rede).
        restore_command="cp -a /deps/vendor ./vendor && composer dump-autoload -q",
        env={"COMPOSER_CACHE_DIR": "/cache"},
    ),
    "go": TechSpec(
        image="puck-checks-go",
        deps_files=("go.mod", "go.sum"),
        deps_command="go mod download",
        restore_command="true",
        env={"GOMODCACHE": "/deps/gomod", "GOFLAGS": "-mod=mod", "GOPROXY": "off",
             "GOTOOLCHAIN": "local"},
    ),
}


# Sobrescritas de ambiente só na etapa de dependências (a única com acesso à internet).
DEPS_NETWORK_ENV = {"go": {"GOPROXY": "https://proxy.golang.org,direct"}}


class SandboxError(RuntimeError):
    pass


def _docker(*args: str, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        ["docker", *args], text=True, capture_output=True, timeout=timeout, check=False
    )
    if check and completed.returncode != 0:
        raise SandboxError(f"docker {' '.join(args[:3])}…: {completed.stderr.strip()[-2000:]}")
    return completed


def tech_spec(tech: str) -> TechSpec:
    if tech not in TECHS:
        raise SandboxError(f"tech desconhecida: {tech} (conhecidas: {', '.join(TECHS)})")
    return TECHS[tech]


def runtime_env(db_host: str | None) -> dict[str, str]:
    """Ambiente que a base técnica promete ao projeto. Segredos novos a cada execução."""
    env = {
        "APP_ENV": "testing",
        "APP_DEBUG": "false",
        "APP_KEY": "base64:" + base64.b64encode(secrets.token_bytes(32)).decode(),
        "APP_PASSWORD_PEPPER": base64.b64encode(secrets.token_bytes(32)).decode(),
        "APP_PASSWORD_PEPPER_VERSION": "1",
        "PORT": str(APP_PORT),
        "LOG_CHANNEL": "stderr",
    }
    if db_host:
        env |= {
            "DB_CONNECTION": "pgsql",
            "DB_HOST": db_host,
            "DB_PORT": "5432",
            "DB_DATABASE": "escola",
            "DB_USERNAME": "escola",
            "DB_PASSWORD": "escola",
        }
    return env


def _env_args(env: dict[str, str]) -> list[str]:
    return [arg for key, value in env.items() for arg in ("-e", f"{key}={value}")]


def deps_volume(tech: str, repo: Path) -> str:
    """Volume com as dependências já baixadas; reaproveitado enquanto o lockfile não mudar."""
    spec = tech_spec(tech)
    digest = hashlib.sha256()
    for name in spec.deps_files:
        path = repo / name
        digest.update(name.encode() + b"\0" + (path.read_bytes() if path.is_file() else b""))
    volume = f"puck-deps-{tech}-{digest.hexdigest()[:16]}"
    probe = _docker("run", "--rm", "-v", f"{volume}:/deps", "busybox", "test", "-f", "/deps/.ok",
                    check=False)
    if probe.returncode == 0:
        return volume
    script = f"cp -a /app/. /work/ && cd /work && {spec.deps_command} && touch /deps/.ok"
    # Única etapa com rede: baixa, mas não executa código do projeto.
    env = spec.env | DEPS_NETWORK_ENV.get(tech, {})
    completed = _docker(
        "run", "--rm", "-w", "/work", "-v", f"{repo.resolve()}:/app:ro", "-v", f"{volume}:/deps",
        "-v", f"puck-cache-{tech}:/cache", *_env_args(env), spec.image, "sh", "-c", script,
        check=False, timeout=1800,
    )
    if completed.returncode != 0:
        _docker("volume", "rm", "-f", volume, check=False)
        raise DependencyError(completed.stdout[-4000:] + completed.stderr[-4000:])
    return volume


class DependencyError(SandboxError):
    """Dependências do projeto não resolvem: falha do projeto, não do harness."""


@dataclass
class Stack:
    """Rede interna + PostgreSQL efêmero; base para checks com banco e para a aplicação."""

    tech: str
    repo: Path
    name: str = field(default_factory=lambda: f"puck-{uuid.uuid4().hex[:10]}")
    with_db: bool = True
    containers: list[str] = field(default_factory=list)
    # Primeiro secretário (contrato HTTP): criado pela aplicação, usado pelo oráculo.
    bootstrap: dict[str, str] = field(default_factory=lambda: {
        "NOME": "Secretaria Inicial",
        "EMAIL": f"secretaria.{secrets.token_hex(4)}@exemplo.test",
        "MATRICULA": f"S{secrets.token_hex(4)}",
        "SENHA": secrets.token_urlsafe(18),
    })

    @property
    def network(self) -> str:
        return f"{self.name}-net"

    @property
    def db_host(self) -> str | None:
        return f"{self.name}-pg" if self.with_db else None

    @property
    def app_host(self) -> str:
        return f"{self.name}-app"

    def start(self) -> None:
        if not self.with_db:
            return
        _docker("network", "create", "--internal", self.network)
        self.containers.append(self.db_host)
        _docker(
            "run", "-d", "--name", self.db_host, "--network", self.network,
            "-e", "POSTGRES_DB=escola", "-e", "POSTGRES_USER=escola",
            "-e", "POSTGRES_PASSWORD=escola", "--tmpfs", "/var/lib/postgresql",
            POSTGRES_IMAGE,
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            ready = _docker("exec", self.db_host, "pg_isready", "-U", "escola", "-d", "escola",
                            check=False)
            if ready.returncode == 0:
                # pg_isready responde antes do initdb terminar a segunda inicialização.
                query = _docker("exec", self.db_host, "psql", "-U", "escola", "-d", "escola",
                                "-c", "select 1", check=False)
                if query.returncode == 0:
                    return
            time.sleep(0.5)
        raise SandboxError("PostgreSQL não ficou pronto em 60 s")

    def stop(self) -> None:
        for container in self.containers:
            _docker("rm", "-f", "-v", container, check=False)
        if self.with_db:
            _docker("network", "rm", self.network, check=False)

    def run_args(self, deps: str, env: dict[str, str]) -> list[str]:
        """Sem banco, nem a rede interna: `--network none`."""
        spec = tech_spec(self.tech)
        network = self.network if self.with_db else "none"
        return [
            "--network", network, "-v", f"{self.repo.resolve()}:/app:ro",
            "-v", f"{deps}:/deps", *_env_args(spec.env | env),
        ]

    def start_app(self, deps: str, timeout: int = 180) -> str:
        """Sobe a aplicação (`make migrate && make run`) e espera `GET /saude` responder 200."""
        spec = tech_spec(self.tech)
        env = runtime_env(self.db_host) | {"APP_ENV": "production"} | {
            f"APP_BOOTSTRAP_{k}": v for k, v in self.bootstrap.items()
        }
        script = (f"cp -a /app/. /work/ && cd /work && {spec.restore_command}"
                  " && make migrate && exec make run")
        self.containers.append(self.app_host)
        _docker("run", "-d", "--name", self.app_host, "-w", "/work",
                *self.run_args(deps, env), spec.image, "sh", "-c", script)
        url = f"http://{self.app_host}:{APP_PORT}"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            probe = _docker("run", "--rm", "--network", self.network, "curlimages/curl:8.16.0",
                            "-sf", "-o", "/dev/null", f"{url}/saude", check=False)
            if probe.returncode == 0:
                return url
            state = _docker("inspect", "-f", "{{.State.Running}}", self.app_host, check=False)
            if state.stdout.strip() != "true":
                break
            time.sleep(1)
        logs = _docker("logs", "--tail", "80", self.app_host, check=False)
        raise AppStartError((logs.stdout + logs.stderr)[-4000:])


class AppStartError(SandboxError):
    """A aplicação não subiu ou não respondeu `/saude`: falha do projeto, não do harness."""


@contextmanager
def stack(tech: str, repo: Path, with_db: bool = True) -> Iterator[Stack]:
    current = Stack(tech=tech, repo=repo, with_db=with_db)
    try:
        current.start()
        yield current
    finally:
        current.stop()


def coverage_metrics(xml_text: str) -> dict[str, int]:
    """Cobertura de linhas (em décimos de %) total e das camadas de domínio + regra."""
    root = ET.fromstring(xml_text)
    total_valid = total_covered = core_valid = core_covered = 0
    for cls in root.iter("class"):
        filename = "/" + cls.get("filename", "")
        # Só as linhas diretas da classe: o bloco <methods> repete as mesmas linhas.
        lines = list(cls.findall("./lines/line"))
        covered = sum(1 for line in lines if int(line.get("hits", "0")) > 0)
        total_valid += len(lines)
        total_covered += covered
        if any(marker in filename for marker in CORE_LAYER_MARKERS):
            core_valid += len(lines)
            core_covered += covered
    metrics = {"coverage_lines": total_valid}
    if total_valid:
        metrics["coverage_permille"] = round(1000 * total_covered / total_valid)
    if core_valid:
        metrics["coverage_core_permille"] = round(1000 * core_covered / core_valid)
    return metrics


def print_metrics(metrics: dict[str, int]) -> None:
    """Formato lido pelo parser `puck_metrics` do CheckRunner."""
    for key, value in sorted(metrics.items()):
        print(f"PUCK_METRIC {key} {value}")


def run_make_target(tech: str, target: str, repo: Path) -> int:
    """Roda `make <target>` do projeto no sandbox. Devolve o exit code do make."""
    spec = tech_spec(tech)
    try:
        deps = deps_volume(tech, repo)
    except DependencyError as exc:
        print(f"Dependências do projeto não resolveram:\n{exc}")
        return 2
    with tempfile.TemporaryDirectory(prefix="puck-out-") as out, stack(
        tech, repo, with_db=target in DB_TARGETS
    ) as current:
        os.chmod(out, 0o777)
        env = runtime_env(current.db_host)
        script = (
            f"cp -a /app/. /work/ && cd /work && {spec.restore_command} && make {target};"
            " status=$?; [ -f build/coverage.xml ] && cp build/coverage.xml /out/; exit $status"
        )
        completed = subprocess.run(
            ["docker", "run", "--rm", "-w", "/work", "-v", f"{out}:/out",
             *current.run_args(deps, env), spec.image, "sh", "-c", script],
            text=True, capture_output=True, check=False,
        )
        print((completed.stdout + "\n" + completed.stderr).strip()[-20000:])
        coverage = Path(out) / "coverage.xml"
        if target == "coverage" and coverage.is_file():
            print_metrics(coverage_metrics(coverage.read_text(encoding="utf-8")))
        return completed.returncode


def run_with_app(tech: str, repo: Path, image: str, command: list[str],
                 extra_env: dict[str, str] | None = None, mounts: list[str] | None = None) -> int:
    """Sobe a aplicação e roda `image command` na mesma rede interna, com `TARGET_URL` definido.

    Usado pelo oráculo HTTP, pelo k6 e pelo ZAP. Exit 3 = aplicação não subiu.
    """
    try:
        deps = deps_volume(tech, repo)
    except DependencyError as exc:
        print(f"Dependências do projeto não resolveram:\n{exc}")
        return 2
    with stack(tech, repo) as current:
        try:
            url = current.start_app(deps)
        except AppStartError as exc:
            print(f"Aplicação não subiu:\n{exc}")
            return 3
        env = {"TARGET_URL": url, **{f"PUCK_BOOTSTRAP_{k}": v for k, v in current.bootstrap.items()},
               **(extra_env or {})}
        volumes = [arg for mount in (mounts or []) for arg in ("-v", mount)]
        completed = subprocess.run(
            ["docker", "run", "--rm", "--network", current.network, *_env_args(env), *volumes,
             image, *command],
            text=True, capture_output=True, check=False,
        )
        print((completed.stdout + "\n" + completed.stderr).strip()[-20000:])
        return completed.returncode


def run_oracle(tech: str, repo: Path) -> int:
    """Suíte de caracterização HTTP (oracle/suite) contra a aplicação no sandbox."""
    mounts = [f"{ROOT / 'oracle' / 'suite'}:/oracle/suite:ro",
              f"{ROOT / 'oracle' / 'dataset'}:/oracle/dataset:ro"]
    return run_with_app(tech, repo, ORACLE_IMAGE, [], mounts=mounts)


HARNESS_IMAGES = {
    **{spec.image: Path("docker") / "checks" / tech for tech, spec in TECHS.items()},
    ORACLE_IMAGE: Path("oracle"),
}


def ensure_images(root: Path = ROOT) -> list[str]:
    """Constrói as imagens do harness que faltarem. Devolve as construídas."""
    built = []
    for image, context in HARNESS_IMAGES.items():
        if _docker("image", "inspect", image, check=False).returncode != 0:
            _docker("build", "-q", "-t", image, str(root / context), timeout=1800)
            built.append(image)
    return built

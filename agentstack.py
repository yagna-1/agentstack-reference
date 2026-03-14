#!/usr/bin/env python3
"""AgentStack reference CLI.

Single-entry command surface for operating the glue stack:
- bootstrap dependencies
- start/stop/view compose services
- run full demo flow
- compile audit JSON into tests
- inspect service health and URLs
- execute commands inside dependency repos
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"
DEPS_DIR = ROOT / "deps"

SERVICE_URLS = {
    "nexusgate": "http://localhost:18088/health",
    "fluxroute-router": "http://localhost:18090/healthz",
    "astragraph-graph": "http://localhost:18080/graphs",
    "astragraph-policy": "http://localhost:18081/policies",
}

REPO_MAP = {
    "nexusgate": DEPS_DIR / "nexusgate",
    "fluxroute": DEPS_DIR / "fluxroute",
    "recast": DEPS_DIR / "recast",
    "mcp-test": DEPS_DIR / "mcp-test",
    "astragraph": DEPS_DIR / "astragraph",
}


def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _color(text: str, code: str) -> str:
    if not _supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def info(msg: str) -> None:
    print(_color("info", "36") + f": {msg}")


def ok(msg: str) -> None:
    print(_color("ok", "32") + f": {msg}")


def warn(msg: str) -> None:
    print(_color("warn", "33") + f": {msg}")


def err(msg: str) -> None:
    print(_color("error", "31") + f": {msg}")


def run(cmd: list[str], cwd: Path | None = None) -> int:
    proc = subprocess.run(cmd, cwd=str(cwd or ROOT))
    return proc.returncode


def require_script(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Missing required script: {path}")


def cmd_doctor(_args: argparse.Namespace) -> int:
    info("Running environment checks...")
    required_bins = ["python3", "git", "docker"]
    missing = []
    for b in required_bins:
        if shutil.which(b):
            ok(f"found: {b}")
        else:
            missing.append(b)
            err(f"missing: {b}")

    compose_ok = run(["docker", "compose", "version"]) == 0
    if compose_ok:
        ok("docker compose is available")
    else:
        err("docker compose is not available")

    daemon_ok = run(["docker", "info"]) == 0
    if daemon_ok:
        ok("docker daemon is reachable")
    else:
        warn("docker daemon is not reachable right now")

    missing_repos = []
    for name, path in REPO_MAP.items():
        if (path / ".git").exists():
            ok(f"deps ready: {name}")
        else:
            missing_repos.append(name)
            warn(f"deps missing: {name} ({path})")

    if missing or not compose_ok:
        return 2
    if missing_repos:
        warn("Run './agentstack bootstrap' to clone missing repos.")
    return 0


def compose_cmd(args: list[str]) -> int:
    return run(["docker", "compose", *args], cwd=ROOT)


def cmd_bootstrap(_args: argparse.Namespace) -> int:
    script = SCRIPTS_DIR / "bootstrap.sh"
    require_script(script)
    return run([str(script)], cwd=ROOT)


def cmd_up(args: argparse.Namespace) -> int:
    cmd = ["up", "-d"]
    if args.build:
        cmd.append("--build")
    if args.tools:
        cmd = ["--profile", "tools", *cmd]
    return compose_cmd(cmd)


def cmd_down(args: argparse.Namespace) -> int:
    cmd = ["down"]
    if args.volumes:
        cmd.append("--volumes")
    return compose_cmd(cmd)


def cmd_ps(_args: argparse.Namespace) -> int:
    return compose_cmd(["ps"])


def cmd_logs(args: argparse.Namespace) -> int:
    cmd = ["logs"]
    if args.follow:
        cmd.append("-f")
    if args.tail:
        cmd.extend(["--tail", str(args.tail)])
    if args.service:
        cmd.append(args.service)
    return compose_cmd(cmd)


def cmd_demo(_args: argparse.Namespace) -> int:
    script = SCRIPTS_DIR / "run.sh"
    require_script(script)
    return run([str(script)], cwd=ROOT)


def cmd_compile(args: argparse.Namespace) -> int:
    script = SCRIPTS_DIR / "audit_to_tests.sh"
    require_script(script)
    cmd = [str(script)]
    if args.audit:
        cmd.append(args.audit)
    return run(cmd, cwd=ROOT)


def cmd_urls(_args: argparse.Namespace) -> int:
    print(
        textwrap.dedent(
            """
            Local service URLs
            ------------------
            NexusGate             http://localhost:18088
            FluxRoute Router      http://localhost:18090
            FluxRoute Control     http://localhost:18091
            AstraGraph Graph      http://localhost:18080
            AstraGraph Policy     http://localhost:18081
            AstraGraph Proxy      http://localhost:17070
            """
        ).strip()
    )
    return 0


def _url_ok(url: str, timeout: float = 2.0) -> bool:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except (urllib.error.URLError, TimeoutError):
        return False


def cmd_health(_args: argparse.Namespace) -> int:
    failed = 0
    for name, url in SERVICE_URLS.items():
        if _url_ok(url):
            ok(f"{name}: {url}")
        else:
            failed += 1
            err(f"{name}: {url}")
    return 1 if failed else 0


def cmd_repo(args: argparse.Namespace) -> int:
    repo = args.repo
    if repo not in REPO_MAP:
        err(f"Unknown repo '{repo}'. Choose one of: {', '.join(REPO_MAP)}")
        return 2
    repo_path = REPO_MAP[repo]
    if not repo_path.exists():
        err(f"Repo not found at {repo_path}. Run './agentstack bootstrap' first.")
        return 2
    if not args.command:
        err("No command provided. Example: ./agentstack repo nexusgate cargo check")
        return 2
    return run(args.command, cwd=repo_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentstack",
        description="Single CLI for the AgentStack reference glue repository.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Validate local prerequisites and deps")
    sub.add_parser("bootstrap", help="Clone or update all five dependency repos")

    p_up = sub.add_parser("up", help="Start compose services")
    p_up.add_argument("--build", action="store_true", help="Build images before starting")
    p_up.add_argument("--tools", action="store_true", help="Enable tools profile")

    p_down = sub.add_parser("down", help="Stop compose services")
    p_down.add_argument("--volumes", action="store_true", help="Also remove volumes")

    sub.add_parser("ps", help="Show compose service status")

    p_logs = sub.add_parser("logs", help="Tail compose logs")
    p_logs.add_argument("service", nargs="?", help="Optional service name")
    p_logs.add_argument("-f", "--follow", action="store_true", help="Follow logs")
    p_logs.add_argument("--tail", type=int, default=100, help="Lines to show (default: 100)")

    sub.add_parser("health", help="Quick health check across stack endpoints")
    sub.add_parser("urls", help="Print key local service URLs")
    sub.add_parser("demo", help="Run full end-to-end demo flow")

    p_compile = sub.add_parser("compile", help="Compile audit JSON into Playwright tests")
    p_compile.add_argument("audit", nargs="?", help="Optional path to audit JSON")

    p_repo = sub.add_parser("repo", help="Run a command inside one dependency repo")
    p_repo.add_argument("repo", help="One of: nexusgate, fluxroute, recast, mcp-test, astragraph")
    p_repo.add_argument("command", nargs=argparse.REMAINDER, help="Command to run")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    cmd = args.cmd
    if cmd == "doctor":
        return cmd_doctor(args)
    if cmd == "bootstrap":
        return cmd_bootstrap(args)
    if cmd == "up":
        return cmd_up(args)
    if cmd == "down":
        return cmd_down(args)
    if cmd == "ps":
        return cmd_ps(args)
    if cmd == "logs":
        return cmd_logs(args)
    if cmd == "health":
        return cmd_health(args)
    if cmd == "urls":
        return cmd_urls(args)
    if cmd == "demo":
        return cmd_demo(args)
    if cmd == "compile":
        return cmd_compile(args)
    if cmd == "repo":
        return cmd_repo(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

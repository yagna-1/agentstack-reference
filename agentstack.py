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
import curses
import json
import os
import shutil
import subprocess
import sys
import textwrap
import threading
import time
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


def run_capture(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc.returncode, proc.stdout


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


def _compose_ps_rows() -> tuple[list[dict], str | None]:
    code, out = run_capture(["docker", "compose", "ps", "--format", "json"], cwd=ROOT)
    if code != 0:
        return [], out.strip() or "docker compose ps failed"
    text = out.strip()
    if not text:
        return [], None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed, None
        return [], "unexpected docker compose ps JSON payload"
    except json.JSONDecodeError:
        # Fallback: some compose versions may output line-delimited JSON.
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except json.JSONDecodeError:
                continue
        if rows:
            return rows, None
        return [], "unable to parse docker compose ps output"


class AgentStackTUI:
    HELP = (
        "q quit | r refresh | u up --build | d down | b bootstrap | m demo | c compile | "
        "h health | j/k move | l toggle logs | : command prompt"
    )

    def __init__(self, stdscr: curses.window):
        self.stdscr = stdscr
        self.running = True
        self.selected_index = 0
        self.service_rows: list[dict] = []
        self.health_rows: list[tuple[str, bool]] = []
        self.status_message = "Loading..."
        self.log_lines: list[str] = []
        self.log_lock = threading.Lock()
        self.log_service = ""
        self.log_proc: subprocess.Popen[str] | None = None
        self.log_thread: threading.Thread | None = None
        self.follow_logs = False
        self.last_refresh = 0.0
        self.command_history: list[str] = []

    def stop_logs(self) -> None:
        if self.log_proc and self.log_proc.poll() is None:
            self.log_proc.terminate()
            try:
                self.log_proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                self.log_proc.kill()
        self.log_proc = None
        self.log_thread = None

    def start_logs(self, service: str) -> None:
        self.stop_logs()
        self.log_service = service
        cmd = ["docker", "compose", "logs", "-f", "--tail", "80", service]
        try:
            self.log_proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            self.append_log(f"[log] failed to start logs: {exc}")
            return

        def _reader() -> None:
            assert self.log_proc is not None
            stream = self.log_proc.stdout
            if stream is None:
                return
            for line in stream:
                if not self.running:
                    break
                self.append_log(line.rstrip("\n"))

        self.log_thread = threading.Thread(target=_reader, daemon=True)
        self.log_thread.start()

    def append_log(self, line: str) -> None:
        with self.log_lock:
            self.log_lines.append(line)
            if len(self.log_lines) > 1500:
                self.log_lines = self.log_lines[-1500:]

    def run_action(self, title: str, cmd: list[str]) -> None:
        self.status_message = f"{title}..."
        code, out = run_capture(cmd, cwd=ROOT)
        if out.strip():
            self.append_log(f"$ {' '.join(cmd)}")
            for line in out.strip().splitlines()[-80:]:
                self.append_log(line)
        if code == 0:
            self.status_message = f"{title}: done"
        else:
            self.status_message = f"{title}: failed (exit {code})"
        self.refresh(force=True)

    def _draw_box(self, y: int, x: int, h: int, w: int, title: str) -> None:
        if h < 2 or w < 2:
            return
        self.stdscr.addstr(y, x, "+" + "-" * (w - 2) + "+")
        for i in range(1, h - 1):
            self.stdscr.addstr(y + i, x, "|")
            self.stdscr.addstr(y + i, x + w - 1, "|")
        self.stdscr.addstr(y + h - 1, x, "+" + "-" * (w - 2) + "+")
        if title and w > 6:
            t = f" {title} "
            self.stdscr.addstr(y, x + 2, t[: w - 4])

    def refresh_health(self) -> None:
        rows = []
        for name, url in SERVICE_URLS.items():
            rows.append((name, _url_ok(url, timeout=1.5)))
        self.health_rows = rows

    def refresh(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self.last_refresh < 1.5):
            return
        self.last_refresh = now
        rows, err_msg = _compose_ps_rows()
        self.service_rows = rows
        if err_msg:
            self.status_message = err_msg
        else:
            self.status_message = f"services: {len(rows)}"
        if self.service_rows and self.selected_index >= len(self.service_rows):
            self.selected_index = max(0, len(self.service_rows) - 1)
        self.refresh_health()

    def _service_name(self, row: dict) -> str:
        name = row.get("Service") or row.get("Name") or row.get("ID") or "unknown"
        if isinstance(name, str):
            return name
        return str(name)

    def selected_service(self) -> str:
        if not self.service_rows:
            return "nexusgate"
        return self._service_name(self.service_rows[self.selected_index])

    def _status_short(self, row: dict) -> str:
        status = row.get("State") or row.get("Status") or "unknown"
        if isinstance(status, str):
            status = status.strip()
            if len(status) > 16:
                return status[:16]
            return status
        return str(status)

    def prompt_command(self) -> None:
        h, w = self.stdscr.getmaxyx()
        prompt = ": "
        self.stdscr.move(h - 1, 0)
        self.stdscr.clrtoeol()
        self.stdscr.addstr(h - 1, 0, prompt)
        curses.echo()
        try:
            raw = self.stdscr.getstr(h - 1, len(prompt), max(4, w - len(prompt) - 2))
        finally:
            curses.noecho()
        try:
            cmd = raw.decode("utf-8").strip()
        except Exception:
            cmd = ""
        if not cmd:
            return
        self.command_history.append(cmd)
        self.append_log(f"> {cmd}")
        self._handle_prompt_command(cmd)

    def _handle_prompt_command(self, cmd: str) -> None:
        parts = cmd.split()
        if not parts:
            return
        head = parts[0]
        if head in ("quit", "q", "exit"):
            self.running = False
            return
        if head == "up":
            self.run_action("compose up", ["docker", "compose", "up", "-d", "--build"])
            return
        if head == "down":
            self.run_action("compose down", ["docker", "compose", "down"])
            return
        if head == "demo":
            self.run_action("demo", [str(SCRIPTS_DIR / "run.sh")])
            return
        if head == "compile":
            extra = parts[1:] if len(parts) > 1 else []
            self.run_action("compile", [str(SCRIPTS_DIR / "audit_to_tests.sh"), *extra])
            return
        if head == "bootstrap":
            self.run_action("bootstrap", [str(SCRIPTS_DIR / "bootstrap.sh")])
            return
        if head == "health":
            self.refresh_health()
            self.status_message = "health refreshed"
            return
        if head == "logs":
            service = parts[1] if len(parts) > 1 else self.selected_service()
            self.follow_logs = True
            self.start_logs(service)
            self.status_message = f"following logs: {service}"
            return
        if head == "repo" and len(parts) >= 3:
            repo = parts[1]
            repo_path = REPO_MAP.get(repo)
            if repo_path is None:
                self.status_message = f"unknown repo: {repo}"
                return
            code, out = run_capture(parts[2:], cwd=repo_path)
            self.append_log(f"$ (repo:{repo}) {' '.join(parts[2:])}")
            if out.strip():
                for line in out.strip().splitlines()[-80:]:
                    self.append_log(line)
            self.status_message = f"repo command exit: {code}"
            return
        self.status_message = f"unknown command: {cmd}"

    def draw(self) -> None:
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        title = " AgentStack Control Center "
        self.stdscr.addstr(0, 0, (title + self.HELP)[: max(0, w - 1)])

        top_h = max(8, min(15, h // 3))
        logs_h = max(8, h - top_h - 3)
        left_w = max(45, min(70, w // 2))
        right_w = max(20, w - left_w - 1)

        self._draw_box(1, 0, top_h, left_w, "Services")
        self._draw_box(1, left_w, top_h, right_w, "Health")
        self._draw_box(1 + top_h, 0, logs_h, w, f"Logs ({self.log_service or 'none'})")

        # Services panel
        row_y = 2
        header = "IDX  SERVICE                          STATUS"
        self.stdscr.addstr(row_y, 2, header[: left_w - 4])
        row_y += 1
        max_rows = top_h - 3
        for i, row in enumerate(self.service_rows[:max_rows]):
            service = self._service_name(row)
            status = self._status_short(row)
            line = f"{i+1:>2}   {service:<30} {status:<16}"
            attr = curses.A_REVERSE if i == self.selected_index else curses.A_NORMAL
            self.stdscr.addstr(row_y + i, 2, line[: left_w - 4], attr)

        if not self.service_rows:
            self.stdscr.addstr(row_y, 2, "No services found (run `up`)", curses.A_DIM)

        # Health panel
        hy = 2
        for name, is_ok in self.health_rows[: top_h - 3]:
            marker = "UP" if is_ok else "DOWN"
            line = f"{name:<20} {marker}"
            self.stdscr.addstr(hy, left_w + 2, line[: right_w - 4])
            hy += 1

        # Logs panel
        with self.log_lock:
            lines = self.log_lines[-(logs_h - 3) :]
        ly = 2 + top_h
        for i, line in enumerate(lines):
            self.stdscr.addstr(ly + i, 2, line[: max(1, w - 4)])

        status = f"status: {self.status_message}"
        self.stdscr.addstr(h - 1, 0, status[: max(0, w - 1)], curses.A_BOLD)
        self.stdscr.refresh()

    def loop(self) -> int:
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)
        self.refresh(force=True)

        while self.running:
            self.refresh()
            self.draw()
            ch = self.stdscr.getch()
            if ch == -1:
                time.sleep(0.08)
                continue
            if ch in (ord("q"), 27):  # q or ESC
                self.running = False
            elif ch in (ord("r"),):
                self.refresh(force=True)
            elif ch in (ord("j"), curses.KEY_DOWN):
                if self.service_rows:
                    self.selected_index = min(len(self.service_rows) - 1, self.selected_index + 1)
            elif ch in (ord("k"), curses.KEY_UP):
                if self.service_rows:
                    self.selected_index = max(0, self.selected_index - 1)
            elif ch == ord("u"):
                self.run_action("compose up", ["docker", "compose", "up", "-d", "--build"])
            elif ch == ord("d"):
                self.run_action("compose down", ["docker", "compose", "down"])
            elif ch == ord("b"):
                self.run_action("bootstrap", [str(SCRIPTS_DIR / "bootstrap.sh")])
            elif ch == ord("m"):
                self.run_action("demo", [str(SCRIPTS_DIR / "run.sh")])
            elif ch == ord("c"):
                self.run_action("compile", [str(SCRIPTS_DIR / "audit_to_tests.sh")])
            elif ch == ord("h"):
                self.refresh_health()
                self.status_message = "health refreshed"
            elif ch == ord("l"):
                if self.follow_logs:
                    self.follow_logs = False
                    self.stop_logs()
                    self.status_message = "log follow stopped"
                else:
                    service = self.selected_service()
                    self.follow_logs = True
                    self.start_logs(service)
                    self.status_message = f"following logs: {service}"
            elif ch == ord(":"):
                self.prompt_command()

        self.stop_logs()
        return 0


def cmd_ui(_args: argparse.Namespace) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        err("ui mode requires an interactive TTY")
        return 2

    def _wrapped(stdscr: curses.window) -> int:
        app = AgentStackTUI(stdscr)
        return app.loop()

    return curses.wrapper(_wrapped)


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
    sub.add_parser("ui", help="Launch interactive terminal control center")

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
    if cmd == "ui":
        return cmd_ui(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Remote Console client for this lab only: one request at a time, every exchange logged.

Usage:
  python -I research/timestop-lab/lab_rc.py procs
  python -I research/timestop-lab/lab_rc.py ready
  python -I research/timestop-lab/lab_rc.py lua LABEL (LUA | @FILE) [--arg NAME=VALUE ...]
                                                [--timeout SECONDS] [--delay SECONDS] [--expect-exit]
  python -I research/timestop-lab/lab_rc.py collect LABEL [--timeout SECONDS]

A request is sent only while this lab's game runs and no other request is pending. A timeout
is recorded and never resent: the game claims a request only while a polling menu renders
(not during a cutscene, for example), so `collect` later picks up the late result of the
same request. --arg values reach the Lua code as strings in the table ARGS; they are encoded
as decimal byte escapes, never as code. --delay waits before sending, for a timed case.
A game that exits can never answer: --expect-exit (for a request that quits the game) and
`collect` end with status "exited" once this lab's game is gone, and move a request file the
game never claimed out of override, so that no later start runs it.
Evidence goes to <lab>/cbr-timestop-output/rc-log/, outside the repository. This client
never starts, stops or clicks a game itself.
The lab is the one CBR_LAB_VARIANT names, as for the PowerShell scripts: the Time Stop lab
(unset or "timestop") or the Time Clocks lab ("timeclocks"); any other value is refused.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

# Variant -> (lab folder, engine name), as in Lab.Common.ps1.
VARIANTS = {"timestop": ("CBR-TimeStop-2.7.3.0", "CBR TimeStop Lab 2730"),
            "timeclocks": ("CBR-TimeClocks-2.7.3.0", "CBR TimeClocks Lab 2730")}
VARIANT = os.environ.get("CBR_LAB_VARIANT") or "timestop"
if VARIANT not in VARIANTS:
    raise SystemExit(f"CBR_RC_ERROR: unknown CBR_LAB_VARIANT {VARIANT!r}")
LAB = Path(os.environ["USERPROFILE"]) / "Games" / VARIANTS[VARIANT][0]
LAB_ID = (VARIANTS[VARIANT][1] + "\n").encode("ascii")
OVERRIDE = LAB / "override"
LOG = LAB / "cbr-timestop-output" / "rc-log"
PENDING = LOG / "pending.json"
COMMAND, CLAIM, RESULT = (OVERRIDE / "eeex_remote_cmd.lua", OVERRIDE / "eeex_remote_cmd.lua.run",
                          OVERRIDE / "eeex_remote_result.json")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")
LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,60}$")
EXIT_POLL = 1.0  # Seconds between process checks while a game may be exiting.


class ClientError(RuntimeError):
    pass


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def assert_lab() -> None:
    marker = LAB / "CBRTSLab.id"
    if not marker.is_file() or marker.read_bytes() != LAB_ID:
        raise ClientError(f"Not the owned lab: {LAB}")


def lua_string(value: str) -> str:
    """Fixed-width decimal escapes: the value can never become Lua code."""
    return '"' + "".join(f"\\{byte:03d}" for byte in value.encode("utf-8")) + '"'


def with_arguments(code: str, arguments: dict[str, str]) -> str:
    """Insert `local ARGS = {...}` after the console's leading --@ directive lines."""
    lines = code.splitlines(keepends=True)
    directives = 0
    while directives < len(lines) and lines[directives].startswith("--@"):
        directives += 1
    table = ", ".join(f"{name} = {lua_string(value)}" for name, value in sorted(arguments.items()))
    return "".join(lines[:directives]) + f"local ARGS = {{{table}}}\n" + "".join(lines[directives:])


def processes() -> list[dict]:
    """Baldur.exe and InfinityLoader.exe with their image paths (CIM), ours marked."""
    script = ("Get-CimInstance Win32_Process -Filter \"Name='Baldur.exe' or Name='InfinityLoader.exe'\" | "
              "Select-Object ProcessId,Name,ExecutablePath,CreationDate | ConvertTo-Json -Compress")
    done = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise ClientError(f"Process query failed: {done.stderr.strip()}")
    found = json.loads(done.stdout) if done.stdout.strip() else []
    found = [found] if isinstance(found, dict) else found
    lab = str(LAB.resolve()).lower() + os.sep
    for entry in found:
        path = (entry.get("ExecutablePath") or "")
        entry["ours"] = bool(path) and path.lower().startswith(lab)
    return found


def record(label: str, entry: dict) -> Path:
    LOG.mkdir(parents=True, exist_ok=True)
    path = LOG / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}-{label}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(entry, handle, indent=1, ensure_ascii=False)
    return path


def wait_result(request: str, timeout: float) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if RESULT.exists():
            try:
                body = RESULT.read_text(encoding="utf-8")
                data = json.loads(body) if body else None
            except (OSError, json.JSONDecodeError):
                data = None  # Still being published; the console renames it into place.
            if data is not None:
                if data.get("id") == request:
                    RESULT.unlink(missing_ok=True)
                    return data
                if data.get("id") is not None:
                    raise ClientError(f"Foreign result {data.get('id')} in the result file; not touched.")
        time.sleep(0.1)
    return None


def game_running() -> bool:
    return any(entry["ours"] and entry["Name"].lower() == "baldur.exe" for entry in processes())


def wait_result_or_exit(request: str, timeout: float) -> tuple[dict | None, bool]:
    """The result, or (None, True) once this lab's game is gone without answering."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = wait_result(request, min(EXIT_POLL, max(deadline - time.time(), 0)))
        if data is not None:
            return data, False
        if not game_running():
            return wait_result(request, 0.2), True  # A result published just before the exit.
    return None, False


def retire_leftovers(request: str, label: str) -> list[str]:
    """After the game exited: move this request's own files out of override (evidence kept)."""
    moved = []
    for path, kind in ((COMMAND, "unclaimed"), (CLAIM, "claimed")):
        if not path.exists():
            continue
        if path.read_text(encoding="utf-8").split("\n", 1)[0] != f"--@id={request}":
            raise ClientError(f"Foreign request file {path.name} in override; not touched.")
        LOG.mkdir(parents=True, exist_ok=True)
        target = LOG / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}-{label}.{kind}.lua"
        os.replace(path, target)
        moved.append(str(target))
    return moved


def require_game() -> list[dict]:
    found = processes()
    games = [entry for entry in found if entry["Name"].lower() == "baldur.exe"]
    ours = [entry for entry in games if entry["ours"]]
    if len(ours) != 1:
        raise ClientError(f"Expected exactly one Baldur.exe from this lab, found: {games}")
    return found


def send(label: str, code: str, source: str | None, timeout: float, delay: float,
         expect_exit: bool = False) -> dict:
    assert_lab()
    if PENDING.exists():
        raise ClientError(f"A request is still pending ({PENDING.read_text(encoding='utf-8').strip()}); "
                          "run `collect` first.")
    for path in (COMMAND, CLAIM):
        if path.exists():
            raise ClientError(f"Console request file present: {path.name}; nothing was overwritten.")
    before = require_game()
    if delay:
        time.sleep(delay)
    request = uuid.uuid4().hex
    LOG.mkdir(parents=True, exist_ok=True)  # Before sending: a timeout must always be able to record pending.
    temporary = OVERRIDE / f"eeex_remote_cmd.tmp.{os.getpid()}"
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(f"--@id={request}\n{code}")
    RESULT.unlink(missing_ok=True)
    sent = time.time()
    os.replace(temporary, COMMAND)
    data, exited = wait_result_or_exit(request, timeout) if expect_exit else (wait_result(request, timeout), False)
    entry = {"label": label, "id": request, "sent_utc": datetime.fromtimestamp(sent, timezone.utc).isoformat(),
             "source": source, "code": code, "processes_before": before}
    if data is None and exited:
        claimed = not COMMAND.exists()
        entry["response"] = {"status": "exited", "claimed": claimed, "retired": retire_leftovers(request, label)}
    elif data is None:
        claimed = not COMMAND.exists()
        entry["response"] = {"status": "timeout", "claimed": claimed}
        PENDING.write_text(json.dumps({"id": request, "label": label, "sent": entry["sent_utc"]}) + "\n",
                           encoding="utf-8")
    else:
        data["_roundtrip_s"] = round(time.time() - sent, 2)
        entry["response"] = data
    if entry["response"].get("status") != "ok":
        entry["processes_after"] = processes()
    entry["log"] = str(record(label, entry))
    return entry


def collect(label: str, timeout: float) -> dict:
    assert_lab()
    if not PENDING.exists():
        raise ClientError("No pending request.")
    pending = json.loads(PENDING.read_text(encoding="utf-8"))
    data, exited = wait_result_or_exit(pending["id"], timeout)
    entry = {"label": label, "collects": pending, "collected_utc": utc()}
    if data is None and exited:
        entry["response"] = {"status": "exited", "claimed": not COMMAND.exists(),
                             "retired": retire_leftovers(pending["id"], label)}
        PENDING.unlink()
    elif data is None:
        entry["response"] = {"status": "timeout", "claimed": not COMMAND.exists()}
    else:
        entry["response"] = data
        PENDING.unlink()
    if entry["response"].get("status") != "ok":
        entry["processes_after"] = processes()
    entry["log"] = str(record(label, entry))
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("procs")
    commands.add_parser("ready")
    lua = commands.add_parser("lua")
    lua.add_argument("label")
    lua.add_argument("code")
    lua.add_argument("--arg", action="append", default=[])
    lua.add_argument("--timeout", type=float, default=15)
    lua.add_argument("--delay", type=float, default=0)
    lua.add_argument("--expect-exit", action="store_true")
    late = commands.add_parser("collect")
    late.add_argument("label")
    late.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args(argv)
    try:
        if args.command == "procs":
            result = processes()
        elif args.command == "ready":
            path = OVERRIDE / "eeex_remote_ready.json"
            result = {"exists": path.exists()}
            if path.exists():
                result.update(raw=path.read_text(encoding="utf-8"), age_s=round(time.time() - path.stat().st_mtime, 1))
        else:
            if not LABEL.match(args.label):
                raise ClientError("Use a simple label.")
            if args.command == "collect":
                result = collect(args.label, args.timeout)
            else:
                source = None
                code = args.code
                if code.startswith("@"):
                    source = code[1:]
                    code = Path(source).read_text(encoding="utf-8")
                values = {}
                for item in args.arg:
                    name, separator, value = item.partition("=")
                    if not separator or not NAME.match(name) or name in values:
                        raise ClientError(f"Invalid --arg {item!r}")
                    values[name] = value
                if values:
                    code = with_arguments(code, values)
                result = send(args.label, code, source, args.timeout, args.delay, args.expect_exit)
    except (ClientError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"CBR_RC_ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1, ensure_ascii=False))
    status = result.get("response", {}).get("status") if isinstance(result, dict) else None
    expected_exit = status == "exited" and getattr(args, "expect_exit", False)
    return 0 if status in (None, "ok") or expected_exit else 1


if __name__ == "__main__":
    raise SystemExit(main())

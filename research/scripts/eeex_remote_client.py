"""One-shot client for the installed EEex Remote Console protocol 1.1.

This is research tooling, not an installer.  It atomically publishes one
transient command into an already authorized game's override IPC directory,
waits for the matching result, prints that JSON, and removes the consumed
result.  ``--file`` sends the file contents; it never copies or indexes the
source as a game resource.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path

PROTOCOL = "1.1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("override", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--code")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--id")
    parser.add_argument("--nowatchdog", action="store_true")
    return parser


def _read_ready(override: Path) -> dict[str, object]:
    ready_path = override / "eeex_remote_ready.json"
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    if ready.get("protocol") != PROTOCOL:
        raise RuntimeError(f"unsupported remote protocol: {ready.get('protocol')!r}")
    if ready.get("disabled") not in (False, None):
        raise RuntimeError(f"remote console disabled: {ready.get('disabled')}")
    return ready


def main() -> int:
    args = _parser().parse_args()
    override = args.override.resolve(strict=True)
    if not override.is_dir():
        raise RuntimeError(f"not an override directory: {override}")
    _read_ready(override)

    command_path = override / "eeex_remote_cmd.lua"
    run_path = override / "eeex_remote_cmd.lua.run"
    result_path = override / "eeex_remote_result.json"
    result_temp = override / "eeex_remote_result.json.tmp"
    occupied = [path.name for path in (command_path, run_path, result_path, result_temp) if path.exists()]
    if occupied:
        raise RuntimeError(f"remote IPC is not idle: {', '.join(occupied)}")

    request_id = args.id or f"cbr-{uuid.uuid4()}"
    code = args.file.resolve(strict=True).read_text(encoding="ascii") if args.file else args.code
    directives = [f"--@id={request_id}"]
    if args.nowatchdog:
        directives.append("--@nowatchdog")
    payload = "\n".join(directives) + "\n" + (code or "") + "\n"

    publish_temp = override / f"eeex_remote_cmd.lua.client-{os.getpid()}.tmp"
    publish_temp.write_text(payload, encoding="utf-8", newline="\n")
    try:
        os.replace(publish_temp, command_path)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            if result_path.exists():
                try:
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    time.sleep(0.05)
                    continue
                if result.get("id") != request_id:
                    raise RuntimeError(
                        f"received result for {result.get('id')!r}, expected {request_id!r}"
                    )
                print(json.dumps(result, ensure_ascii=True, sort_keys=True))
                result_path.unlink()
                return 0 if result.get("status") == "ok" else 2
            time.sleep(0.05)
        raise TimeoutError(f"no EEex result for {request_id} within {args.timeout:.1f}s")
    finally:
        publish_temp.unlink(missing_ok=True)
        if command_path.exists():
            text = command_path.read_text(encoding="utf-8", errors="replace")
            if f"--@id={request_id}" in text:
                command_path.unlink()


if __name__ == "__main__":
    raise SystemExit(main())

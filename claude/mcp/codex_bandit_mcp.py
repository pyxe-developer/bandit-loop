#!/usr/bin/env python3
"""MCP wrapper for Codex Bandit script entrypoints.

The wrapper delegates to scripts as subprocesses. It does not reimplement
Codex Bandit behavior.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOL_TO_SCRIPT = {
    "codex_bandit_orchestrate": "orchestrate-assisted",
    "codex_bandit_route_card": "route-card",
    "codex_bandit_evidence_ledger": "evidence-ledger",
    "codex_bandit_verify_stage": "verify-stage",
    "codex_bandit_review_package": "review-package",
    "codex_bandit_delivery_operation": "delivery-operation",
}


def run_script(tool_name: str, request_json: str) -> subprocess.CompletedProcess[str]:
    script = TOOL_TO_SCRIPT.get(tool_name)
    if not script:
        raise ValueError(f"unknown Codex Bandit MCP tool: {tool_name}")
    return subprocess.run(
        [str(ROOT / "scripts" / script)],
        input=request_json,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT),
        check=False,
    )


def direct_call(tool_name: str) -> int:
    request_json = sys.stdin.read()
    proc = run_script(tool_name, request_json)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, separator, value = line.decode("ascii", errors="replace").partition(":")
        if separator:
            headers[key.lower().strip()] = value.strip()
    raw_length = headers.get("content-length")
    if raw_length is None:
        raise ValueError("MCP message is missing Content-Length")
    body = sys.stdin.buffer.read(int(raw_length))
    if len(body) != int(raw_length):
        raise ValueError("MCP message ended before Content-Length bytes were read")
    value = json.loads(body.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("MCP message must be a JSON object")
    return value


def send_message(message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def tool_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"request": {"type": "object"}},
        "required": ["request"],
        "additionalProperties": False,
    }


def tool_list() -> list[dict[str, Any]]:
    descriptions = {
        "codex_bandit_orchestrate": "Delegate to scripts/orchestrate-assisted.",
        "codex_bandit_route_card": "Delegate to scripts/route-card.",
        "codex_bandit_evidence_ledger": "Delegate to scripts/evidence-ledger.",
        "codex_bandit_verify_stage": "Delegate to scripts/verify-stage.",
        "codex_bandit_review_package": "Delegate to scripts/review-package.",
        "codex_bandit_delivery_operation": "Delegate to scripts/delivery-operation.",
    }
    return [
        {
            "name": name,
            "description": descriptions[name],
            "inputSchema": tool_schema(),
        }
        for name in sorted(TOOL_TO_SCRIPT)
    ]


def rpc_result(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def rpc_error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")
    if method == "initialize":
        return rpc_result(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "codex-bandit", "version": "0.1.0"},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return rpc_result(message_id, {"tools": tool_list()})
    if method == "tools/call":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        name = params.get("name")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        request = arguments.get("request")
        if not isinstance(name, str) or name not in TOOL_TO_SCRIPT:
            return rpc_error(message_id, -32602, "unknown Codex Bandit tool")
        if not isinstance(request, dict):
            return rpc_error(message_id, -32602, "arguments.request must be an object")
        request_json = json.dumps(request, separators=(",", ":"), ensure_ascii=False)
        proc = run_script(name, request_json)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"raw_stdout": proc.stdout}
        return rpc_result(
            message_id,
            {
                "content": [{"type": "text", "text": proc.stdout}],
                "structuredContent": {
                    "script": TOOL_TO_SCRIPT[name],
                    "exit_code": proc.returncode,
                    "response": payload,
                    "stderr": proc.stderr,
                },
                "isError": proc.returncode != 0,
            },
        )
    return rpc_error(message_id, -32601, f"unsupported method: {method}")


def stdio_server() -> int:
    while True:
        try:
            message = read_message()
        except (ValueError, json.JSONDecodeError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if message is None:
            return 0
        response = handle_message(message)
        if response is not None:
            send_message(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--call", choices=sorted(TOOL_TO_SCRIPT), help="Delegate stdin to a script and emit the script response unchanged.")
    args = parser.parse_args()
    if args.call:
        return direct_call(args.call)
    return stdio_server()


if __name__ == "__main__":
    raise SystemExit(main())

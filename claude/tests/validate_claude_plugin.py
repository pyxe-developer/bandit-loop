#!/usr/bin/env python3
"""Validate the Claude Code-specific packaging and MCP surface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent


def fail(message: str) -> None:
    raise AssertionError(message)


def read_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        fail(f"{path} is missing YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError:
        fail(f"{path} has unterminated YAML frontmatter")
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    return fields


def frame(message: dict) -> bytes:
    body = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def parse_frames(raw: bytes) -> list[dict]:
    messages: list[dict] = []
    position = 0
    while position < len(raw):
        header_end = raw.find(b"\r\n\r\n", position)
        if header_end == -1:
            fail("MCP server emitted an incomplete header")
        headers = raw[position:header_end].decode("ascii").split("\r\n")
        length = next(
            int(line.split(":", 1)[1].strip())
            for line in headers
            if line.lower().startswith("content-length:")
        )
        start = header_end + 4
        body = raw[start : start + length]
        if len(body) != length:
            fail("MCP server emitted a truncated body")
        messages.append(json.loads(body.decode("utf-8")))
        position = start + length
    return messages


def check_packaging() -> None:
    manifest = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "codex-bandit"
    assert manifest["hooks"] == "./hooks/hooks.json"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert (ROOT / manifest["hooks"][2:]).is_file()
    assert (ROOT / manifest["mcpServers"][2:]).is_file()

    skill_names = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}
    expected_skills = {
        "orchestrate",
        "plan-work-item",
        "write-red-tests",
        "implement-green",
        "adversarial-gate",
        "prepare-pr",
        "land-and-deploy",
        "closeout-retro",
    }
    assert skill_names == expected_skills, (skill_names, expected_skills)
    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        fields = read_frontmatter(path)
        assert fields.get("name"), path
        assert fields.get("description"), path

    agent_names: set[str] = set()
    for path in sorted((ROOT / "agents").glob("*.md")):
        fields = read_frontmatter(path)
        name = fields.get("name")
        assert name and name not in agent_names, path
        assert fields.get("description"), path
        agent_names.add(name)
    assert len(agent_names) == 7

    assert not (ROOT / "scripts/install-agents").exists()
    assert not (ROOT / "scripts/install-git-hooks").exists()

    marketplace = json.loads((REPO_ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert marketplace["plugins"][0]["source"] == "./claude"


def check_mcp_stream() -> None:
    messages = b"".join(
        [
            frame(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {},
                }
            ),
            frame({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
        ]
    )
    proc = subprocess.run(
        [sys.executable, str(ROOT / "mcp/codex_bandit_mcp.py")],
        input=messages,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    responses = parse_frames(proc.stdout)
    assert len(responses) == 2, responses
    assert responses[0]["id"] == 1
    tools = responses[1]["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert names == {
        "codex_bandit_orchestrate",
        "codex_bandit_route_card",
        "codex_bandit_evidence_ledger",
        "codex_bandit_verify_stage",
        "codex_bandit_review_package",
        "codex_bandit_delivery_operation",
    }, names


def main() -> int:
    check_packaging()
    check_mcp_stream()
    print(json.dumps({"ok": True, "plugin": str(ROOT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

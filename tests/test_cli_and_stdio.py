"""CLI helpers and a real stdio handshake against the server process (no API key, no network)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None

from miragea_voice_mcp import __version__
from miragea_voice_mcp.cli import CLIENTS, UVX_ARGS, config_snippet, main

EXPECTED_TOOLS = {
    "miragea_get_capabilities",
    "miragea_list_voices",
    "miragea_text_to_speech",
    "miragea_transcribe",
    "miragea_script_to_voiceover",
    "miragea_get_task",
    "miragea_list_tasks",
}


@pytest.mark.parametrize("client", CLIENTS)
def test_config_snippets_are_valid(client):
    snippet = config_snippet(client)
    assert "miragea-voice-mcp" in snippet and "MIRAGEA_API_KEY" in snippet
    if client in ("claude-desktop", "cursor", "windsurf", "vscode"):
        json.loads(snippet)
    if client == "codex" and tomllib is not None:
        data = tomllib.loads(snippet)
        assert data["mcp_servers"]["miragea-voice"]["args"] == UVX_ARGS


def test_print_config(capsys):
    assert main(["--print-config", "cursor"]) == 0
    assert json.loads(capsys.readouterr().out)["mcpServers"]["miragea-voice"]["command"] == "uvx"


def test_check_without_key(monkeypatch, capsys):
    monkeypatch.delenv("MIRAGEA_API_KEY", raising=False)
    assert main(["--check"]) == 2
    assert "MIRAGEA_API_KEY is not set" in capsys.readouterr().err


def _rpc(proc, payload):
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def _read(proc, want_id):
    while True:
        line = proc.stdout.readline()
        if not line:
            raise AssertionError("server closed stdout: " + proc.stderr.read())
        msg = json.loads(line)
        if msg.get("id") == want_id:
            return msg


def test_stdio_handshake_lists_tools_without_key():
    env = {k: v for k, v in os.environ.items() if k != "MIRAGEA_API_KEY"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "miragea_voice_mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    try:
        _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "0"}}})
        init = _read(proc, 1)
        assert init["result"]["serverInfo"]["name"] == "miragea-voice"
        assert "miragea_get_capabilities" in init["result"].get("instructions", "")
        _rpc(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = {t["name"]: t for t in _read(proc, 2)["result"]["tools"]}
        assert set(tools) == EXPECTED_TOOLS
        assert tools["miragea_get_capabilities"]["annotations"]["readOnlyHint"] is True
        assert "actor_id" in tools["miragea_text_to_speech"]["inputSchema"]["properties"]
        # calling a tool without a key returns a helpful tool error, not a crash
        _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "miragea_get_capabilities", "arguments": {}}})
        res = _read(proc, 3)
        text = json.dumps(res)
        assert "MIRAGEA_API_KEY is not set" in text
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=10)


@pytest.mark.skipif(tomllib is None, reason="tomllib needs Python 3.11+")
def test_version_is_consistent():
    root = os.path.dirname(os.path.dirname(__file__))
    with open(os.path.join(root, "pyproject.toml"), "rb") as fh:
        assert tomllib.load(fh)["project"]["version"] == __version__
    with open(os.path.join(root, "server.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["version"] == __version__
    assert data["packages"][0]["version"] == __version__
    assert len(data["description"]) <= 100
    with open(os.path.join(root, "README.md"), encoding="utf-8") as fh:
        assert f"mcp-name: {data['name']}" in fh.read()

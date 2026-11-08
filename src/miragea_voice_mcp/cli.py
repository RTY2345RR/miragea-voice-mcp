"""Command line entry point: `tts-mcp-server` (alias `miragea-voice-mcp`) runs the stdio server.

Extras:
  tts-mcp-server --check                 verify the key and reach /capabilities (read-only)
  tts-mcp-server --print-config cursor   print a ready-to-paste client config
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import __version__

CLIENTS = ("claude-desktop", "cursor", "claude-code", "codex", "vscode", "windsurf")
KEY_PLACEHOLDER = "<your-miragea-api-key>"
PACKAGE = "tts-mcp-server"
SERVER_KEY = "tts"
UVX_ARGS = [PACKAGE]


def config_snippet(client: str) -> str:
    server = {"command": "uvx", "args": list(UVX_ARGS), "env": {"MIRAGEA_API_KEY": KEY_PLACEHOLDER}}
    if client in ("claude-desktop", "cursor", "windsurf"):
        return json.dumps({"mcpServers": {SERVER_KEY: server}}, indent=2)
    if client == "vscode":
        return json.dumps(
            {"servers": {SERVER_KEY: {"type": "stdio", **server}}},
            indent=2,
        )
    if client == "claude-code":
        return f"claude mcp add {SERVER_KEY} -s user -e MIRAGEA_API_KEY={KEY_PLACEHOLDER} -- uvx {PACKAGE}"
    if client == "codex":
        return (
            f"[mcp_servers.{SERVER_KEY}]\n"
            'command = "uvx"\n'
            f'args = {json.dumps(UVX_ARGS)}\n'
            "tool_timeout_sec = 900\n"
            f'env = {{ MIRAGEA_API_KEY = "{KEY_PLACEHOLDER}" }}'
        )
    raise ValueError(f"Unknown client {client!r}; choose from {', '.join(CLIENTS)}.")


async def _check() -> int:
    from .client import MirageaClient, MirageaError
    from .config import MISSING_KEY_MESSAGE, ConfigError, load_settings

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    if not settings.has_key:
        print(MISSING_KEY_MESSAGE, file=sys.stderr)
        return 2
    print(f"MIRAGEA_API_KEY: set ({len(settings.api_key)} chars, value hidden)", file=sys.stderr)
    print(f"API root: {settings.base_url}", file=sys.stderr)
    print(f"Output folder: {settings.output_dir}", file=sys.stderr)
    try:
        async with MirageaClient(settings) as client:
            caps = await client.capabilities()
    except MirageaError as exc:
        print(f"API check failed: {exc}", file=sys.stderr)
        return 2
    audio = caps.get("audio") or {}
    models = [m.get("id") for m in audio.get("models") or [] if isinstance(m, dict)]
    print(
        f"OK: models={models} default={audio.get('default_model')} "
        f"max_text_length={audio.get('max_text_length')}",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tts-mcp-server",
        description="TTS MCP server: text-to-speech, voiceover, voice cloning and subtitles for AI agents (stdio, Miragea voice engine).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--check", action="store_true", help="verify MIRAGEA_API_KEY and API reachability (read-only, creates no job)")
    parser.add_argument("--print-config", choices=CLIENTS, metavar="CLIENT", help=f"print config for: {', '.join(CLIENTS)}")
    args = parser.parse_args(argv)

    if args.print_config:
        print(config_snippet(args.print_config))
        return 0
    if args.check:
        return asyncio.run(_check())

    from .server import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Command line entry point: `miragea-voice-mcp` runs the stdio server.

Extras:
  miragea-voice-mcp --check                 verify the key and reach /capabilities (read-only)
  miragea-voice-mcp --print-config cursor   print a ready-to-paste client config
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import __version__

CLIENTS = ("claude-desktop", "cursor", "claude-code", "codex", "vscode", "windsurf")
KEY_PLACEHOLDER = "<your-miragea-api-key>"
# Installed from GitHub until the PyPI release is live; then this becomes ["miragea-voice-mcp"].
GIT_SOURCE = "git+https://github.com/RTY2345RR/miragea-voice-mcp"
UVX_ARGS = ["--from", GIT_SOURCE, "miragea-voice-mcp"]


def config_snippet(client: str) -> str:
    server = {"command": "uvx", "args": list(UVX_ARGS), "env": {"MIRAGEA_API_KEY": KEY_PLACEHOLDER}}
    if client in ("claude-desktop", "cursor", "windsurf"):
        return json.dumps({"mcpServers": {"miragea-voice": server}}, indent=2)
    if client == "vscode":
        return json.dumps(
            {"servers": {"miragea-voice": {"type": "stdio", **server}}},
            indent=2,
        )
    if client == "claude-code":
        return f"claude mcp add miragea-voice -s user -e MIRAGEA_API_KEY={KEY_PLACEHOLDER} -- uvx --from {GIT_SOURCE} miragea-voice-mcp"
    if client == "codex":
        return (
            "[mcp_servers.miragea-voice]\n"
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
        prog="miragea-voice-mcp",
        description="MCP server for AI voiceovers and subtitles with the Miragea API (stdio).",
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

# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-08

### Added
- stdio MCP server `miragea-voice-mcp`, runnable with `uvx --from git+https://github.com/RTY2345RR/miragea-voice-mcp miragea-voice-mcp` (PyPI release `uvx miragea-voice-mcp` coming soon).
- Tools: `miragea_get_capabilities`, `miragea_list_voices`, `miragea_text_to_speech`,
  `miragea_transcribe`, `miragea_script_to_voiceover`, `miragea_get_task`, `miragea_list_tasks`.
- One-shot script → voiceover + SRT/VTT captions, with script-accurate caption wording and
  short-form cue splitting (`max_caption_chars`).
- Local WebVTT rendering from Miragea's timed segments.
- No duplicate jobs on retry: idempotency keys on every job, automatic retries reuse the same key,
  timeouts return a resumable `task_id`, pre-flight validation against live capabilities.
- `--check` (read-only key/API check) and `--print-config` for Claude Desktop, Claude Code, Cursor,
  Codex, VS Code and Windsurf.
- Compatible with MCP Python SDK 1.x (`FastMCP`) and 2.x (`MCPServer`).
- Companion Agent Skill `skills/miragea-voiceover`.
- Registry metadata: `server.json`, `smithery.yaml`, `glama.json`, `llms.txt`.

[Unreleased]: https://github.com/RTY2345RR/miragea-voice-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/RTY2345RR/miragea-voice-mcp/releases/tag/v0.1.0

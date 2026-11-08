# TTS MCP Server — text-to-speech, AI voiceover, voice cloning and SRT/VTT subtitles for Claude, Cursor and Codex

[![CI](https://github.com/RTY2345RR/miragea-voice-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/RTY2345RR/miragea-voice-mcp/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/RTY2345RR/miragea-voice-mcp)](https://github.com/RTY2345RR/miragea-voice-mcp/releases)
[![PyPI](https://img.shields.io/pypi/v/tts-mcp-server.svg)](https://pypi.org/project/tts-mcp-server/)
[![Docker](https://img.shields.io/badge/docker-miragea%2Ftts--mcp--server-2496ED.svg)](https://hub.docker.com/r/miragea/tts-mcp-server)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Hugging Face Space](https://img.shields.io/badge/%F0%9F%A4%97%20Demo-Hugging%20Face%20Space-yellow.svg)](https://huggingface.co/spaces/miragea/miragea-voice-mcp)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-stdio-black.svg)](https://modelcontextprotocol.io)

**tts-mcp-server is an open-source text-to-speech (TTS) MCP server that gives AI agents a voice.** It lets Claude Desktop, Claude Code, Cursor, OpenAI Codex, VS Code and Windsurf turn a script into a narration audio file (MP3, WAV, FLAC, Opus, AAC or PCM) plus matching SRT and WebVTT subtitles in one [Model Context Protocol](https://modelcontextprotocol.io) tool call. It also clones a voice from a reference audio URL, uses the voices saved in your account, and transcribes any local audio or video file into captions. Text-to-speech, voice cloning and speech recognition run on the [Miragea](https://miragea.ai) voice engine. Install it with one command, `uvx tts-mcp-server`; it needs only a `MIRAGEA_API_KEY` and is MIT licensed.

**Install:** `uvx tts-mcp-server` · `pip install tts-mcp-server` · `docker run -i --rm -e MIRAGEA_API_KEY miragea/tts-mcp-server` · **Try it in the browser:** [live demo on Hugging Face Spaces](https://huggingface.co/spaces/miragea/miragea-voice-mcp) · **Source:** [github.com/RTY2345RR/miragea-voice-mcp](https://github.com/RTY2345RR/miragea-voice-mcp)

> Formerly published as `miragea-voice-mcp`. The `miragea-voice-mcp` command is still installed as an alias, so existing configs keep working.

<!-- mcp-name: io.github.RTY2345RR/tts-mcp-server -->

![Terminal screenshot: installing the voiceover and captions MCP server with uvx from GitHub, printing the Claude Code config, and listing its 7 MCP tools (text-to-speech, voice cloning, transcription to SRT/VTT)](docs/images/voiceover-captions-mcp-server-terminal-demo.svg)

```text
You:    Turn script.txt into a calm voiceover with captions for a YouTube Short.
Agent:  miragea_script_to_voiceover(script_file="script.txt", actor_id="…", tags=["calm"])
        → ~/Miragea/my-short.mp3  ~/Miragea/my-short.srt  ~/Miragea/my-short.vtt
```

---

## Contents

- [How it works](#how-it-works)
- [Features](#features)
- [Quickstart (60 seconds)](#quickstart-60-seconds)
- [Client setup: Claude Desktop, Claude Code, Cursor, Codex, VS Code, Windsurf](#client-setup)
- [Tools reference](#tools-reference)
- [Examples with real output](#examples)
- [Example prompts](#example-prompts)
- [Configuration](#configuration)
- [How it compares](#how-it-compares)
- [FAQ](#faq)
- [Troubleshooting](#troubleshooting)
- [Agent Skill](#companion-agent-skill)
- [Development](#development)
- [Links](#links)

## How it works

![Architecture diagram of the voiceover and captions MCP server: an AI agent such as Claude, Cursor or Codex calls tts-mcp-server over MCP stdio; the server calls the Miragea voice engine for text-to-speech, voice cloning and speech recognition, and writes MP3 audio plus SRT and WebVTT captions](docs/images/voiceover-captions-mcp-architecture-diagram.svg)

1. Your AI agent (Claude Desktop, Claude Code, Cursor, OpenAI Codex, VS Code or Windsurf) calls a tool such as `miragea_script_to_voiceover` over the Model Context Protocol (stdio).
2. The server checks the request against the live voice-engine capabilities (models, emotion tags, formats, text length) and adds an idempotency key.
3. The [Miragea](https://miragea.ai) voice engine generates the narration (or clones a voice from your reference clip), then runs speech recognition on the new audio for timestamps.
4. The server writes `.mp3` + `.srt` + `.vtt` side by side, with captions that keep your exact script wording, ready to import into your video editor.

## Features

- **Script → voiceover + captions in one call.** `miragea_script_to_voiceover` generates the narration, times captions by running Miragea speech recognition on the new audio, and writes `.mp3` + `.srt` + `.vtt` side by side, ready for CapCut, Premiere Pro, DaVinci Resolve, YouTube, TikTok, Reels and Shorts.
- **Captions spelled like your script.** Recognition can mishear brand names ("Miragea" → "Mirage ear"). By default the server keeps the recognized *timing* but puts back your *exact script wording*, snapping cue breaks to sentence ends.
- **Short-form friendly caption lengths.** `max_caption_chars` (default 42 for scripts) splits long cues and shares their time by length, so captions stay readable on vertical video.
- **Two voice sources.** Use a voice already saved in your Miragea account (`actor_id`), or clone from a public reference audio URL (`reference_audio_url` + optional `reference_text`).
- **Expressive or standard models, emotion tags, speed 0.25–4×.** Options are read live from `/capabilities`, and every argument is validated *before* a job is submitted.
- **Subtitles for any audio or video file.** `miragea_transcribe` uploads mp3/wav/m4a/mp4/mov… and saves SRT, VTT, TXT or JSON (text, language, timed segments).
- **No duplicate jobs on retry.** Every job carries an `Idempotency-Key`; network errors and 502/503/504 are retried with the *same* key, so a retry never creates a second job. Timeouts return the `task_id` so the agent resumes with `miragea_get_task` instead of resubmitting.
- **Never overwrites files.** Existing outputs get `-2`, `-3`… suffixes.
- **Secret-safe.** The key is read from the environment, never logged, never echoed in errors, never sent to the audio download host, and API redirects are not followed.
- **Starts without a key.** Tool listing works with no key (handy for registries and inspectors); calls return a clear "set MIRAGEA_API_KEY" message.
- **Works on MCP Python SDK 1.x and 2.x**, Python 3.10–3.13, macOS, Windows and Linux. Two dependencies: `mcp` and `httpx`.

## Quickstart (60 seconds)

1. **Get a voice-engine key.** The server uses [Miragea](https://miragea.ai) for voiceover, voice cloning and recognition. Sign in and create an API key at **[miragea.ai/workspace/api](https://miragea.ai/workspace/api)**. Setup guide: **Install https://miragea.ai/skills/miragea-audio/install.md**.
2. **Install [uv](https://docs.astral.sh/uv/)** if you don't have it: `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows).
3. **Add the server to your client** (Claude Code shown; others below):

```bash
claude mcp add tts -s user -e MIRAGEA_API_KEY=<your-miragea-api-key> -- uvx tts-mcp-server
```

4. **Verify** (read-only, creates no job):

```bash
MIRAGEA_API_KEY=<your-miragea-api-key> uvx tts-mcp-server --check
```

Then ask your agent: *"List my Miragea voices, then read 'Welcome back to the channel!' in the first English one."*

> Prefer pip? `pip install tts-mcp-server` and use `"command": "tts-mcp-server"` with no `args` in the snippets below. Prefer Docker? Use `"command": "docker"` with `"args": ["run", "-i", "--rm", "-e", "MIRAGEA_API_KEY", "-v", "/path/to/output:/data", "miragea/tts-mcp-server"]`.

## Client setup

Print any snippet with `uvx tts-mcp-server --print-config <client>` (`claude-desktop`, `cursor`, `claude-code`, `codex`, `vscode`, `windsurf`). Replace `<your-miragea-api-key>` and restart the client.

### Claude Desktop

Settings → Developer → Edit Config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "tts": {
      "command": "uvx",
      "args": ["tts-mcp-server"],
      "env": { "MIRAGEA_API_KEY": "<your-miragea-api-key>" }
    }
  }
}
```

### Claude Code

```bash
claude mcp add tts -s user -e MIRAGEA_API_KEY=<your-miragea-api-key> -- uvx tts-mcp-server
```

### Cursor

`~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project) — same JSON as Claude Desktop.

### OpenAI Codex (CLI and IDE extension)

`~/.codex/config.toml`:

```toml
[mcp_servers.tts]
command = "uvx"
args = ["tts-mcp-server"]
tool_timeout_sec = 900
env = { MIRAGEA_API_KEY = "<your-miragea-api-key>" }
```

`tool_timeout_sec` matters: voiceover jobs can take longer than Codex's default tool timeout.

### VS Code (Copilot agent mode)

`.vscode/mcp.json`:

```json
{
  "servers": {
    "tts": {
      "type": "stdio",
      "command": "uvx",
      "args": ["tts-mcp-server"],
      "env": { "MIRAGEA_API_KEY": "<your-miragea-api-key>" }
    }
  }
}
```

### Windsurf

`~/.codeium/windsurf/mcp_config.json` — same JSON as Claude Desktop.

## Tools reference

| Tool | What it does |
| --- | --- |
| `miragea_get_capabilities` | Live models (`expressive`, `standard`), emotion tags per model, formats, speed range, max characters per request, subtitle formats and upload limits. **Call first.** |
| `miragea_list_voices` | Voices saved in your account (`actor_id`, `name`, `language`), paged; `search` finds a name across pages. |
| `miragea_text_to_speech` | Text (or `text_file`) → audio file. Voice via `actor_id` **or** `reference_audio_url` (+ `reference_text`). Options: `model`, `tags`, `speed`, `format`, `language`, `output_path`, `wait`. |
| `miragea_transcribe` | Local audio/video → subtitles in `srt`, `vtt`, `txt`, `json`; `max_caption_chars` for short cues. |
| `miragea_script_to_voiceover` | Script → audio + captions (SRT + VTT by default). `caption_text="script"` (exact wording) or `"recognized"`; `captions=false` for audio only; `name`, `output_dir`. |
| `miragea_get_task` | Check or resume any job by `task_id`; with `wait=true` it saves the audio or subtitles. |
| `miragea_list_tasks` | Recent jobs, newest first. |

Every generation tool returns `task_id`, `status` and the `idempotency_key` it used, plus the saved file paths.

## Examples

Real outputs from this server (Miragea voice engine), committed in [`examples/`](https://github.com/RTY2345RR/miragea-voice-mcp/tree/main/examples). Voices are cloned from [CMU ARCTIC](http://www.festvox.org/cmu_arctic/) reference clips (licensed free for any use); the audiobook clip is from [LibriSpeech](https://www.openslr.org/12) (CC BY 4.0).

| Example | Prompt to your agent | Tools | Output |
| --- | --- | --- | --- |
| [YouTube voiceover with SRT](https://github.com/RTY2345RR/miragea-voice-mcp/tree/main/examples/youtube-voiceover-srt) | "Read `script.txt` as a YouTube intro in a clear male voice and give me SRT captions." | `miragea_text_to_speech` → `miragea_transcribe` | [MP3](https://github.com/RTY2345RR/miragea-voice-mcp/raw/main/examples/youtube-voiceover-srt/youtube-intro.mp3) · [SRT](https://github.com/RTY2345RR/miragea-voice-mcp/blob/main/examples/youtube-voiceover-srt/youtube-intro.srt) |
| [Two-voice dialogue](https://github.com/RTY2345RR/miragea-voice-mcp/tree/main/examples/two-voice-dialogue) | "Make a two-line dialogue: one male, one female voice, then join them with captions." | `miragea_text_to_speech` ×2 (voice cloning) | [MP3](https://github.com/RTY2345RR/miragea-voice-mcp/raw/main/examples/two-voice-dialogue/dialogue.mp3) · [SRT](https://github.com/RTY2345RR/miragea-voice-mcp/blob/main/examples/two-voice-dialogue/dialogue.srt) |
| [Transcribe audio to captions](https://github.com/RTY2345RR/miragea-voice-mcp/tree/main/examples/transcribe-to-captions) | "Create SRT and VTT subtitles for `audiobook-clip.flac`." | `miragea_transcribe` | [SRT](https://github.com/RTY2345RR/miragea-voice-mcp/blob/main/examples/transcribe-to-captions/audiobook-clip.srt) · [VTT](https://github.com/RTY2345RR/miragea-voice-mcp/blob/main/examples/transcribe-to-captions/audiobook-clip.vtt) |

Transcription output (`audiobook-clip.srt`), with words kept whole across cues:

```srt
1
00:00:00,480 --> 00:00:01,987
He hoped there would be stew for

2
00:00:01,987 --> 00:00:03,987
dinner, turnips and carrots, and

3
00:00:03,987 --> 00:00:06,063
bruised potatoes and fat mutton
```

## Example prompts

- "Make a 30-second product-ad voiceover from `ad.txt` with my *Nova* voice, happy tone, 1.1× speed, and give me SRT + VTT with short captions."
- "Clone the voice at `https://example.com/me.wav` (it says: 'Hi, I'm Sam and this is my test.') and narrate `intro.md` as WAV."
- "Create subtitles for `~/Videos/vlog.mp4` as SRT and VTT."
- "That voiceover timed out — resume task `…` and save it to `~/Desktop/episode-3.mp3`."
- "What models and emotion tags does my Miragea account have, and how many characters can I send per request?"

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `MIRAGEA_API_KEY` | — (required for calls) | Your key from [miragea.ai/workspace/api](https://miragea.ai/workspace/api). |
| `MIRAGEA_OUTPUT_DIR` | `~/Miragea` | Where relative output paths and default file names go. Absolute paths are used as given. |
| `MIRAGEA_BASE_URL` | `https://miragea.ai/v1` | API root including `/v1` (for private deployments). |
| `MIRAGEA_WAIT_TIMEOUT` | `600` | Max seconds a tool waits for a job before returning its `task_id`. |
| `MIRAGEA_HTTP_TIMEOUT` | `60` | Per-request HTTP timeout in seconds. |

## How it compares

Honest snapshot from each project's public README (November 2026). "–" means not offered or not documented.

| | **This server** | [elevenlabs-mcp](https://github.com/elevenlabs/elevenlabs-mcp) (local) | [AllVoiceLab-MCP](https://github.com/allvoicelab/AllVoiceLab-MCP) | [better-tts-mcp](https://github.com/CatVinci-Studio/better-tts-mcp) |
| --- | --- | --- | --- | --- |
| Status | Active | Deprecated in favor of ElevenLabs' hosted MCP | Active | Active |
| Voice engine | Miragea | ElevenLabs API | AllVoiceLab API | Microsoft Edge read-aloud (unofficial, no key) |
| One-command install | `uvx tts-mcp-server` | `uvx elevenlabs-mcp` | `uvx allvoicelab-mcp` | `uvx better-tts-mcp` |
| Required config | 1 env var | 1 env var | Key **and** matching region domain | None |
| Ready snippets for Claude Desktop / Claude Code / Cursor / Codex / VS Code / Windsurf | All six + `--print-config` | Claude Desktop + `--print` helper | Claude Desktop, Cursor | Claude Desktop, Claude Code |
| Voice cloning from a sample | Reference audio URL | Yes (voice library) | Yes | – |
| Subtitles from your own audio/video (speech) | SRT, VTT, TXT, JSON | Speech-to-text (text) | OCR of burned-in subtitles | – |
| Script → audio **+ captions** in one call | Yes | – | – | Audio + SRT |
| Captions keep exact script spelling | Yes | – | – | Yes (from TTS) |
| No duplicate jobs on retry (idempotency keys) + resume by task ID | Yes | – | – | – |

Where the others are ahead: ElevenLabs and AllVoiceLab cover more audio tasks (sound effects, voice changer, dubbing, agents), and better-tts-mcp needs no key and offers batch and multi-voice synthesis. This server stays focused on the video-creator loop of **script → voiceover → captions** and does that one loop end to end.

## FAQ

### What is a TTS MCP server?
A TTS (text-to-speech) MCP server is a small program that exposes speech synthesis as tools over the Model Context Protocol, so an AI agent such as Claude or Cursor can turn text into an audio file on request. tts-mcp-server adds voice cloning, speech-to-text subtitles and a one-call script → voiceover + SRT/VTT workflow on top.

### How do I install a text to speech MCP server in Claude Code?
Run `claude mcp add tts -s user -e MIRAGEA_API_KEY=<your-miragea-api-key> -- uvx tts-mcp-server`, then ask Claude to "read this paragraph aloud and save it as MP3". Use `uvx tts-mcp-server --print-config <client>` for Claude Desktop, Cursor, Codex, VS Code or Windsurf.

### Is there a free text to speech MCP server?
The server itself is free, open-source software (MIT). Speech is generated by the Miragea voice engine, so you need a Miragea API key. If you need a keyless option, [better-tts-mcp](https://github.com/CatVinci-Studio/better-tts-mcp) uses Microsoft Edge read-aloud, and [kokoro-tts-mcp](https://github.com/mberg/kokoro-tts-mcp) runs a local model; neither does voice cloning or subtitles from your own audio.

### Is this an alternative to the ElevenLabs MCP server?
Yes, for the voiceover use case. Like [elevenlabs-mcp](https://github.com/elevenlabs/elevenlabs-mcp) it installs with `uvx` and gives agents text-to-speech and voice cloning; unlike it, one tool call returns the audio together with SRT/VTT captions that keep your exact script wording. ElevenLabs covers more audio tasks (sound effects, voice changer, conversational agents); see [How it compares](#how-it-compares).

### How do I add text-to-speech to Claude Desktop?
Add the `tts` block from [Claude Desktop](#claude-desktop) to `claude_desktop_config.json`, put your Miragea API key in `env`, and restart Claude. Claude can then call `miragea_text_to_speech` and save MP3 files to `~/Miragea`.

### How do I generate SRT subtitles from a video with an AI agent?
Ask the agent to run `miragea_transcribe` on the file (for example, *"make SRT and VTT subtitles for ~/Videos/clip.mp4"*). The server uploads it to Miragea speech recognition and writes `clip.srt` / `clip.vtt`.

### Can an MCP server make a voiceover with matching captions for YouTube Shorts or TikTok?
Yes. `miragea_script_to_voiceover` returns the audio plus SRT/VTT captions timed to that audio, with cues capped at 42 characters by default for vertical video. Import both into CapCut, Premiere Pro or DaVinci Resolve.

### Does it support voice cloning?
Yes. Pass `reference_audio_url` (a public http(s) link to a clean sample) and, ideally, `reference_text` with the exact words spoken in it. Supplying the exact text gives the most faithful clone; if you omit it, Miragea recognizes it automatically. Only clone voices you have the right to use.

### Does it work with Cursor, Claude Code and OpenAI Codex?
Yes, with any MCP client that supports stdio servers. Run `uvx tts-mcp-server --print-config cursor` (or `claude-code`, `codex`, `vscode`, `windsurf`, `claude-desktop`) for a ready snippet.

### Which audio formats can I export?
MP3 (default), WAV, FLAC, Opus, AAC and PCM. Subtitles: SRT, WebVTT, plain text, and JSON with timed segments.

### Can I use it without an API key or with another TTS engine?
No. Miragea is the only voice engine; there is no hidden fallback. Without a key the server still starts and lists its tools, and every call explains how to add the key.

### Is my API key safe?
The key stays in your local MCP config or environment. The server never prints or logs it, redacts it from errors, sends it only to the Miragea API root (redirects are refused), and never sends it to the audio download URL.

### What happens if a long voiceover times out?
The job keeps running on Miragea. The tool returns the `task_id`; ask the agent to call `miragea_get_task` with `wait=true` to download the result. Don't resubmit, because that would create a duplicate job.

### Can I use it in Python scripts or n8n instead of chat?
Any MCP-capable runtime works. For plain scripts, call the Miragea REST API directly ([guide](https://miragea.ai/v1/guide), [OpenAPI schema](https://miragea.ai/v1/schema)).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `MIRAGEA_API_KEY is not set` | Add the key to the server's `env` block (not your shell profile, for GUI clients) and fully restart the client. |
| `HTTP 401 invalid_api_key` | The key is wrong or revoked. Create a new one at [miragea.ai/workspace/api](https://miragea.ai/workspace/api). Run `uvx tts-mcp-server --check`. |
| `HTTP 403` | The account has no API access right now; check it in your Miragea account. `cloudflare_blocked` means a proxy or VPN is being challenged; try another network. |
| `HTTP 429` | Rate-limited or an account limit was reached. Check your Miragea account, or wait and retry. |
| `Text is N characters but this account allows M` | Split the script into parts under `audio.max_text_length` and generate them one by one. |
| `wait_timeout` | The job is still running. Use `miragea_get_task` with the returned `task_id`. Raise `MIRAGEA_WAIT_TIMEOUT` and your client's tool timeout (Codex: `tool_timeout_sec`). |
| Client tool call times out first | Call with `wait=false`, then poll with `miragea_get_task`. |
| `spawn uvx ENOENT` | The GUI app can't find `uvx`. Use its absolute path (`which uvx` / `where uvx`) as `command`. |
| `Tag(s) … are not available` | Tags are per model. List them with `miragea_get_capabilities`. |
| `reference_audio_url must be a public http(s) URL` | Miragea downloads the sample server-side. Upload it somewhere public (not `localhost`, not a file path). |
| Where are my files? | `~/Miragea` by default, or `MIRAGEA_OUTPUT_DIR`. Each tool returns the exact path. |

Logs go to stderr, which your client keeps (Claude Desktop on macOS: `~/Library/Logs/Claude/mcp-server-tts.log`).

## Companion Agent Skill

[`skills/miragea-voiceover/SKILL.md`](skills/miragea-voiceover/SKILL.md) is an [Agent Skill](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills) that teaches Claude a script-to-voiceover workflow on top of these tools: tightening a script for speech, choosing a voice and tone, confirming long jobs first, and delivering audio and captions for each platform. Copy the folder into `~/.claude/skills/` (Claude Code) or upload it as a skill in Claude. It is also published on its own in [RTY2345RR/miragea-agent-skills](https://github.com/RTY2345RR/miragea-agent-skills) with install steps for Claude Code, Codex and Cursor.

## Development

```bash
git clone https://github.com/RTY2345RR/miragea-voice-mcp && cd miragea-voice-mcp
uv venv && uv pip install -e ".[dev]"
pytest                                   # offline; HTTP is mocked
npx @modelcontextprotocol/inspector uvx --from . tts-mcp-server
```

The server wraps only the documented Miragea endpoints: `GET /capabilities`, `GET /actors`, `POST /audio/generations`, `POST /subtitles/recognitions`, `GET /tasks/{id}`, `GET /tasks` ([API guide](https://miragea.ai/v1/guide)). VTT and short-cue splitting are local formatting of Miragea's timed segments.

## Links

- GitHub: https://github.com/RTY2345RR/miragea-voice-mcp
- Live demo (Hugging Face Space): https://huggingface.co/spaces/miragea/miragea-voice-mcp
- Agent Skills: https://github.com/RTY2345RR/miragea-agent-skills
- Miragea API keys: https://miragea.ai/workspace/api
- PyPI: https://pypi.org/project/tts-mcp-server/
- Docker Hub: https://hub.docker.com/r/miragea/tts-mcp-server

## License

[MIT](LICENSE). "Miragea" is the voice engine this server connects to (voiceover, voice cloning, speech recognition). Use cloned voices only with the speaker's consent.

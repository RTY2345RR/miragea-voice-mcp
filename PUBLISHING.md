# Publishing checklist

Everything below assumes the GitHub repository is **`github.com/RTY2345RR/miragea-voice-mcp`**.
If it ever moves to another owner, replace
`RTY2345RR/miragea-voice-mcp` and `io.github.RTY2345RR/` with your owner in: `server.json` (`name`,
`repository.url`), `README.md` (the `mcp-name:` comment and the links), `pyproject.toml`
(`[project.urls]`), `llms.txt`, `CHANGELOG.md`, `glama.json` (`maintainers`) and
`src/miragea_voice_mcp/client.py` (`USER_AGENT`). Then run `pytest`, which checks that the
README `mcp-name` matches `server.json`.

## 1. GitHub repository

**Description** (paste into *About*):

> Voiceover & captions MCP server for AI agents: turn a script into narration + SRT/VTT subtitles from Claude, Cursor and Codex. Voice cloning, emotion tags, transcription. Miragea voice engine.

**Website:** `https://huggingface.co/spaces/miragea/miragea-voice-mcp` (live demo)

**Topics** (20, GitHub's maximum):

```
mcp  mcp-server  model-context-protocol  text-to-speech  tts  voiceover  ai-voice
voice-cloning  subtitles  srt  webvtt  captions  speech-to-text  transcription
claude  claude-code  cursor  codex  video-editing  youtube-shorts
```

CLI: `gh repo edit RTY2345RR/miragea-voice-mcp --description "…" --homepage https://huggingface.co/spaces/miragea/miragea-voice-mcp --add-topic mcp --add-topic mcp-server …` (one `--add-topic` per topic).

**Release:** tag `v0.1.0`, title "v0.1.0 — script to voiceover + captions", and paste the CHANGELOG section as the body.

Also: enable Discussions, upload a social preview image (1280×640) showing the script → mp3 + srt flow, and pin the repo on the profile.

## 2. PyPI (`tts-mcp-server`)

Recommended: **trusted publishing** (no token stored anywhere).

1. Sign in at pypi.org → *Your account → Publishing → Add a new pending publisher*:
   project `tts-mcp-server`, owner `RTY2345RR`, repo `miragea-voice-mcp`, workflow `publish.yml`, environment `pypi`.
2. On GitHub: *Settings → Environments → New environment* named `pypi`.
3. Run *Actions → Publish → Run workflow* (or add a `release: published` trigger to `.github/workflows/publish.yml`). It builds the package, uploads it to PyPI, then publishes to the MCP Registry (step 3).

Manual alternative:

```bash
uv build                 # dist/tts_mcp_server-0.1.1-py3-none-any.whl + .tar.gz
uvx twine check dist/*
uvx twine upload dist/*  # needs a PyPI API token
```

Verify: `uvx tts-mcp-server --version` on a clean machine.

## 3. Official MCP Registry (registry.modelcontextprotocol.io)

The registry checks that the PyPI README contains `<!-- mcp-name: io.github.RTY2345RR/tts-mcp-server -->` (already in `README.md`), so publish to PyPI first.

```bash
# install the publisher CLI (macOS: brew install mcp-publisher)
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher
sudo mv mcp-publisher /usr/local/bin/

cd miragea-voice-mcp
mcp-publisher login github        # sign in as GitHub user `RTY2345RR` (io.github.RTY2345RR namespace)
mcp-publisher publish             # reads ./server.json
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.RTY2345RR/tts-mcp-server"
```

CI does the same with `mcp-publisher login github-oidc` after each release. For every new version, bump `version` in `pyproject.toml`, `src/miragea_voice_mcp/__init__.py` and both places in `server.json` (the tests enforce this).

Optional: owning `miragea.ai` allows the namespace `ai.miragea/voice` via DNS verification (`mcp-publisher login dns --domain miragea.ai …`). Change `name` and the README `mcp-name` together if you switch.

Many directories (PulseMCP and others) import from the official registry, so this step also feeds them.

## 4. Smithery (smithery.ai)

1. Sign in at https://smithery.ai with the GitHub account that owns the repo.
2. Choose **Publish / Add server** → select `RTY2345RR/miragea-voice-mcp`.
3. Smithery reads `smithery.yaml` (stdio; config field `mirageaApiKey` maps to `MIRAGEA_API_KEY`) and builds with the root `Dockerfile`. If the UI asks for a deployment type, choose local/stdio.
4. After the build passes, open the server page, check that all 7 tools are listed (they list without a key), and add the description, the demo homepage and the topics.

## 5. Glama (glama.ai/mcp/servers)

1. Go to https://glama.ai/mcp/servers → **Add Server** → submit `https://github.com/RTY2345RR/miragea-voice-mcp`.
2. `glama.json` lists `RTY2345RR` as maintainer, so sign in with that GitHub account and **Claim** the server.
3. Glama builds the `Dockerfile` and runs an introspection check. It passes without a key because the server starts and lists tools without one. In the server's admin settings, set `MIRAGEA_API_KEY` as a placeholder or a test key if you want the "tested" badge.
4. Copy the score badge for the awesome-mcp-servers PR:
   `[![RTY2345RR/miragea-voice-mcp MCP server](https://glama.ai/mcp/servers/RTY2345RR/miragea-voice-mcp/badges/score.svg)](https://glama.ai/mcp/servers/RTY2345RR/miragea-voice-mcp)`

## 6. mcp.so

1. Open https://mcp.so and click **Submit** (top navigation).
2. Type: MCP Server. Name: `Voiceover & Captions MCP (Miragea voice engine)`. URL: the GitHub repo.
3. Description: the GitHub description above. Tags: text-to-speech, voiceover, subtitles, captions, voice-cloning.
4. Server config: paste the Claude Desktop JSON from the README.
   Fallback if the form is unavailable: open an issue in mcp.so's GitHub repository with the same details.

## 7. PulseMCP

PulseMCP ingests the official registry, so the listing usually appears within about a week of step 3. To speed it up or correct details, use https://www.pulsemcp.com/submit with the GitHub URL and the description above.

## 8. awesome-mcp-servers (punkpeye) pull request

Do this after Glama lists the server, because entries there carry the Glama score badge.

```bash
gh repo fork punkpeye/awesome-mcp-servers --clone && cd awesome-mcp-servers
git checkout -b add-miragea-voice-mcp
```

In `README.md`, under **🎧 Text-to-Speech**, insert this line in alphabetical order (after `mberg/kokoro-tts-mcp`, before `transcribe-app/mcp-transcribe`):

```markdown
- [RTY2345RR/miragea-voice-mcp](https://github.com/RTY2345RR/miragea-voice-mcp) [![RTY2345RR/miragea-voice-mcp MCP server](https://glama.ai/mcp/servers/RTY2345RR/miragea-voice-mcp/badges/score.svg)](https://glama.ai/mcp/servers/RTY2345RR/miragea-voice-mcp) 🎖️ 🐍 ☁️ 🍎 🪟 🐧 - Voiceover & captions for AI agents: script to narration plus SRT/VTT subtitles, voice cloning from a reference URL, emotion tags, and subtitles for any audio or video file (Miragea voice engine).
```

```bash
git commit -am "Add RTY2345RR/miragea-voice-mcp to Text-to-Speech"
git push -u origin add-miragea-voice-mcp
gh pr create --repo punkpeye/awesome-mcp-servers --title "Add tts-mcp-server (text-to-speech, voiceover + subtitles)" \
  --body "Voiceover & captions MCP server (Python, stdio, MIT, Miragea voice engine). Script → voiceover + SRT/VTT captions, voice cloning, transcription. Listed on Glama."
```

Their CONTRIBUTING notes that PRs opened by an automated agent can append `🤖🤖🤖` to the title for a fast-tracked review. Use it only when an agent actually opens the PR. Disclose that you maintain the project, since 🎖️ marks an official implementation.

## 9. More places worth a listing (optional)

- **Anthropic Agent Skills:** publish `skills/miragea-voiceover` in the README and to skill directories such as skillsmp.com, and add it to community `awesome-claude-skills` lists via PR.
- **MCP directories:** mcpservers.org, mcpmarket.com, cursor.directory (MCP section), LobeHub MCP marketplace. Each has a "Submit" form; reuse the description above.
- **Docker MCP Catalog** (`docker/mcp-registry` PR): uses the `Dockerfile` in this repo.

## Before each release

```bash
pytest
uv build && uvx twine check dist/*
python -c "import json;d=json.load(open('server.json'));assert len(d['description'])<=100"
```

Then optionally run a real smoke test with a key, using a short test line:

```bash
MIRAGEA_API_KEY=… uvx tts-mcp-server --check   # read-only
# in your MCP client: "Use miragea_text_to_speech to say 'Hi' with my first voice"
```

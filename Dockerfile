# Minimal image for registries that build MCP servers in containers (Glama, Smithery).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MIRAGEA_OUTPUT_DIR=/data
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && mkdir -p /data
VOLUME ["/data"]
LABEL io.modelcontextprotocol.server.name="io.github.RTY2345RR/tts-mcp-server"
ENTRYPOINT ["tts-mcp-server"]

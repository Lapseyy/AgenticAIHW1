# Build stage: install Python dependencies into /install
FROM python:3.13-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage
FROM python:3.13-slim
WORKDIR /app

# Node.js runs the filesystem and Tavily MCP servers. They are installed once here
# (pinned) so cold starts don't download them with npx.
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && \
    rm -rf /var/lib/apt/lists/* && \
    npm install -g @modelcontextprotocol/server-filesystem@1.0.0 tavily-mcp@0.2.22 && \
    npm cache clean --force

# Packages go to /usr/local (not /root/.local) so the non-root user can read them.
COPY --from=build /install /usr/local

# The fetch server's readabilipy library runs `npm install` inside site-packages on the
# first fetch. The non-root user can't write there (EACCES), and the unpinned install pulls
# packages that need Node 22+. Install its Node dependencies now, as root, pinned to
# versions that support Debian's Node 20.
RUN cd /usr/local/lib/python3.13/site-packages/readabilipy/javascript && \
    npm install --omit=dev --no-audit --no-fund jsdom@26 @mozilla/readability@0.6 minimist@1 && \
    npm cache clean --force

COPY . .

RUN useradd -m appuser && mkdir -p /app/workspace && chown -R appuser:appuser /app
USER appuser

ENV WORKSPACE_DIR=/app/workspace \
    MCP_SERVERS_CONFIG=/app/mcp_config.json \
    PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "main.py"]
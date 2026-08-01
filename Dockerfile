# =============================================================================
# Stage 1: Build the React frontend (webui)
# =============================================================================
FROM node:20-bookworm-slim AS node-build

WORKDIR /app/webui

# Copy dependency manifests first (leverage Docker layer caching)
COPY webui/package.json webui/package-lock.json ./
RUN npm ci

# Copy the rest of the webui source and build
COPY webui/ ./
RUN npm run build

# =============================================================================
# Stage 2: Python runtime — final image
# =============================================================================
FROM python:3.11-slim

# Install system dependencies
#   git        — required by the git_operation tool
#   build-essential — native deps for chromadb (e.g., setproctitle, grpcio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python package manifests and source
COPY pyproject.toml ./
COPY src/ ./src/

# Install the codingkit package with all extras
RUN pip install --no-cache-dir -e ".[all]"

# Copy the pre-built frontend from stage 1
COPY --from=node-build /app/webui/dist/ ./webui/dist/

EXPOSE 8080

ENTRYPOINT ["codingkit"]
CMD ["web", "--port", "8080"]
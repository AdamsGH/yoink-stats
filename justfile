set dotenv-load := true
set shell := ["bash", "-cu"]

root := justfile_directory() + "/../.."

# List available recipes
default:
    @just --list

# Run stats plugin tests inside Docker against the shared yoink_test DB.
# Usage: just test [path]
test *args="src/tests":
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose -f "{{root}}/docker-compose.yaml" exec -T yoink-postgres \
        psql -U yoink -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='yoink_test'" | grep -q 1 \
        || docker compose -f "{{root}}/docker-compose.yaml" exec -T yoink-postgres \
            psql -U yoink -d postgres -c \
            "CREATE DATABASE yoink_test OWNER yoink;"
    docker run --rm \
        --network yoink \
        -v "{{justfile_directory()}}/src:/app/plugins/yoink-stats/src:ro" \
        -v "{{justfile_directory()}}/pyproject.toml:/app/plugins/yoink-stats/pyproject.toml:ro" \
        yoink/yoink:latest \
        sh -c "uv pip install --system pytest pytest-asyncio -q && python -m pytest /app/plugins/yoink-stats/{{args}} -v --tb=short"

# Lint with ruff
lint:
    ruff check src/

# Format with ruff
fmt:
    ruff format src/

#! /usr/bin/env bash

set -e
set -x

cd backend
FASTAPI_ENV=development uv run python -c "import app.main; import json; print(json.dumps(app.main.app.openapi()))" > ../openapi.json
cd ..
mv openapi.json frontend/
bun run --filter frontend generate-client
# Biome is configured to ignore src/client, so strip trailing blanks here.
find frontend/src/client -type f -name '*.ts' -exec sed -i.bak 's/[[:blank:]]*$//' {} +
find frontend/src/client -type f -name '*.ts.bak' -delete
bun run lint

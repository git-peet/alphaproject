#!/usr/bin/env bash
# Run the backend suite against a disposable PostgreSQL database.
# No xtrace: DATABASE_URL is a secret and must never be echoed.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir/.."

export FASTAPI_ENV=development

# The app resolves settings from ../.env internally; print only the database name.
app_db_name="$(uv run --frozen python -c 'from app.core.config import settings; print(settings.DATABASE_URL.path.lstrip("/"))')"

if [[ -z "$app_db_name" ]]; then
    echo "ERROR: could not resolve the application database name; refusing to run." >&2
    exit 1
fi

if [[ -n "${TEST_DB_NAME:-}" ]]; then
    test_db_name="$TEST_DB_NAME"
else
    suffix="$(date -u +%H%M%S)_$$_${RANDOM}"
    test_db_name="${app_db_name:0:40}_test_${suffix}"
fi

if [[ ! "$test_db_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "ERROR: target '$test_db_name' is not a safe PostgreSQL identifier; refusing to run." >&2
    exit 1
fi
if (( ${#test_db_name} > 63 )); then
    echo "ERROR: target '$test_db_name' exceeds PostgreSQL's 63-byte identifier limit; refusing to run." >&2
    exit 1
fi
if [[ "$test_db_name" == "$app_db_name" ]]; then
    echo "ERROR: target '$test_db_name' equals the application database; refusing to run." >&2
    exit 1
fi
# A derived target always has the _test_ marker followed by a per-run suffix.
if [[ "$test_db_name" != *_test_* ]]; then
    echo "ERROR: target '$test_db_name' does not contain the '_test_' marker; refusing to run." >&2
    exit 1
fi

# Marker is written only after CREATE DATABASE succeeds, so a stale database is
# refused rather than dropped by this run's cleanup.
marker="$(mktemp)"

cleanup() {
    local rc=$?
    set +e
    trap - EXIT INT TERM
    if [[ -s "$marker" ]]; then
        uv run --frozen python - "$test_db_name" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

from app.core.config import settings

target = sys.argv[1]
parts = urlsplit(str(settings.DATABASE_URL))
# libpq does not understand SQLAlchemy's +psycopg scheme suffix.
pg_scheme = parts.scheme.replace("+psycopg", "")
admin_url = urlunsplit((pg_scheme, parts.netloc, "/postgres", parts.query, ""))
try:
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(target)
            )
        )
except Exception as exc:
    print(
        f"ERROR: could not drop disposable database {target} "
        f"({type(exc).__name__})",
        file=sys.stderr,
    )
    sys.exit(1)
print(f"Dropped disposable database {target}")
PY
        if [[ $? -ne 0 ]]; then
            echo "ERROR: cleanup failed for '$test_db_name'; check the database manually." >&2
        fi
    fi
    rm -f "$marker"
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

uv run --frozen python - "$test_db_name" "$marker" "$@" <<'PY'
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

from app.core.config import settings

target = sys.argv[1]
marker = Path(sys.argv[2])
pytest_args = sys.argv[3:]

parts = urlsplit(str(settings.DATABASE_URL))
if not parts.scheme or not parts.netloc or not parts.path:
    print(
        "ERROR: cannot parse the application DATABASE_URL safely; refusing to run.",
        file=sys.stderr,
    )
    sys.exit(1)


def url_for(db_name: str, sqlalchemy: bool = True) -> str:
    scheme = parts.scheme if sqlalchemy else parts.scheme.replace("+psycopg", "")
    return urlunsplit((scheme, parts.netloc, f"/{db_name}", parts.query, ""))


try:
    with psycopg.connect(url_for("postgres", False), autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
except Exception as exc:
    print(
        f"ERROR: could not create disposable database {target} ({type(exc).__name__})",
        file=sys.stderr,
    )
    sys.exit(1)
marker.write_text(target)
print(f"Created disposable database {target}")

env = dict(os.environ)
env["DATABASE_URL"] = url_for(target)
env["FASTAPI_ENV"] = "development"

rc = subprocess.call([sys.executable, "-m", "alembic", "upgrade", "head"], env=env)
if rc != 0:
    print(
        "ERROR: alembic upgrade head failed; disposable database will be dropped",
        file=sys.stderr,
    )
    sys.exit(rc)

rc = subprocess.call([sys.executable, "-m", "pytest", "tests/", *pytest_args], env=env)
sys.exit(rc)
PY

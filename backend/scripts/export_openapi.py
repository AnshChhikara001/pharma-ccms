"""Dump the OpenAPI schema to backend/openapi.json.

This is step one of the contract pipeline:

    Pydantic schemas -> FastAPI -> openapi.json -> openapi-typescript
                                                     -> frontend/src/types/api.ts

Exporting to a file rather than scraping a running server means CI can verify the
contract without booting anything, and the schema is diffable in review: a PR
that changes the API surface shows exactly what changed.

Usage:
    python -m scripts.export_openapi
"""

import json
import sys
from pathlib import Path

from app.main import app

OUTPUT = Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> int:
    schema = app.openapi()
    # sort_keys keeps the output stable across runs, so a no-op export produces
    # an empty git diff instead of noise.
    OUTPUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    paths = len(schema.get("paths", {}))
    models = len(schema.get("components", {}).get("schemas", {}))
    print(f"Wrote {OUTPUT} — {paths} paths, {models} component schemas")
    return 0


if __name__ == "__main__":
    sys.exit(main())

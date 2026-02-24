"""Export the OpenAPI schema from the FastAPI app to a static JSON file.

Usage (local, requires dependencies installed):
    cd server && python scripts/export_openapi.py

Usage (Docker, if local deps are not installed):
    curl -s http://127.0.0.1:8080/openapi.json | python3 -m json.tool > openapi.json

Outputs:
    server/openapi.json
"""
import json
import os
import sys

# Add the server directory to the Python path so we can import 'src'
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

# Set a dummy DATABASE_URL to avoid connection errors during import.
# The app.openapi() method only inspects route metadata; it does NOT
# connect to the database or start the lifespan.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")

from src.main import app  # noqa: E402

schema = app.openapi()

output_path = os.path.join(server_dir, "openapi.json")
with open(output_path, "w") as f:
    json.dump(schema, f, indent=2)
    f.write("\n")

# Summary
paths = list(schema.get("paths", {}).keys())
print(f"Exported OpenAPI {schema['openapi']} spec to {output_path}")
print(f"  Title:   {schema['info']['title']}")
print(f"  Version: {schema['info']['version']}")
print(f"  Paths:   {len(paths)}")
for p in sorted(paths):
    methods = ", ".join(m.upper() for m in schema["paths"][p])
    print(f"    {methods:8s} {p}")

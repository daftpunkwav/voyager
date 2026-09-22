"""One-shot minimal reproduction: which tool-schema construct makes the
provider's anthropic endpoint answer 400 InvalidParameter (as the task
subagent's full face does). Tests one variable per request: untyped
property / `default` member / cleaned schema. Provider + key are read
read-only from the live data dir. Run: `uv run python tools/diag_subagent_400.py`."""

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"'))

from platform_secrets import SecretStore


def call(base, key, model, input_schema, label):
    body = {
        "model": model,
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "Call the tool once with any value."}],
        "tools": [
            {
                "name": "probe_tool",
                "description": "probe",
                "input_schema": input_schema,
            }
        ],
    }
    req = urllib.request.Request(
        f"{base.rstrip('/')}/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60):
            print(f"[{label}] HTTP 200")
            return True
    except urllib.error.HTTPError as exc:
        print(f"[{label}] HTTP {exc.code}: {exc.read()[:150]!r}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] transport error: {exc}")
        return None


def main():
    con = sqlite3.connect(f"file:{ROOT / 'data/runtime/llm/llm.db'}?mode=ro", uri=True)
    pid, base, fmt = con.execute(
        "SELECT id, base_url, api_format FROM providers WHERE id='7ab76aaac1d2'"
    ).fetchone()
    con.close()
    # the session model comes from llm.default_model (settings), not the
    # provider row's default_model (empty here)
    model = "glm-5.3-flash"
    print(f"provider={pid} fmt={fmt} model={model}")

    key = SecretStore(ROOT / "data/runtime/secrets.db").get(f"llm.provider.{pid}.api_key") or ""
    print("key loaded:", bool(key))

    call(
        base,
        key,
        model,
        {"type": "object", "properties": {"value": {}}, "required": ["value"]},
        "A: untyped property {} (the schema gen_mcp used to emit)",
    )
    call(
        base,
        key,
        model,
        {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
        "B: same but typed (the fallback gen_mcp emits now)",
    )
    call(
        base,
        key,
        model,
        {
            "type": "object",
            "properties": {"q": {"type": "string", "default": ""}},
            "required": [],
        },
        "C: `default` member present (the member _clean_anthropic_schema strips)",
    )
    call(
        base,
        key,
        model,
        {"type": "object", "properties": {"q": {"type": "string"}}, "required": []},
        "D: default stripped (the schema gen_mcp emits now)",
    )


if __name__ == "__main__":
    main()

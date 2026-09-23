"""LLM service data access (separate namespace): provider metadata +
usage rows.

Responsibilities:
- Provider metadata table: upsert / get / list / delete with a thread lock
- Usage rows written directly at call sites, plus day-grouped usage stats

Secret boundary: API keys are never stored in this database — keys live in
platform/secrets. This DB holds all provider metadata plus the usage table,
which carries metering written directly at call sites (not parsed from logs).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS providers (
    id           TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    preset_id    TEXT NOT NULL DEFAULT '',
    base_url     TEXT NOT NULL,
    api_format   TEXT NOT NULL,
    models       TEXT NOT NULL DEFAULT '[]',
    models_meta  TEXT NOT NULL DEFAULT '{}',
    enabled      INTEGER NOT NULL DEFAULT 1,
    custom       INTEGER NOT NULL DEFAULT 0,
    created_ts   REAL NOT NULL,
    updated_ts   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL NOT NULL,
    provider_id   TEXT NOT NULL,
    model         TEXT NOT NULL,
    caller        TEXT NOT NULL DEFAULT '',
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    ok            INTEGER NOT NULL DEFAULT 1,
    reasoning_tokens  INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts);
"""

_COLS = (
    "id",
    "display_name",
    "preset_id",
    "base_url",
    "api_format",
    "models",
    "models_meta",
    "enabled",
    "custom",
    "created_ts",
    "updated_ts",
)


def _split_row(
    *, input: Any, output: Any, cached: Any, calls: Any, reasoning: Any = 0, **keys: Any
) -> dict[str, Any]:
    """One aggregate row of the usage contract: identity keys plus the token
    split (cached is a subset of input; completion equals output; reasoning
    is a subset of output reported by thinking models)."""
    inp, outp, cach = int(input), int(output), int(cached)
    row = {
        **keys,
        "input": inp,
        "output": outp,
        "total_tokens": inp + outp,
        "prompt_cached_tokens": cach,
        "prompt_uncached_tokens": max(inp - cach, 0),
        "completion_tokens": outp,
        "calls": int(calls),
    }
    if int(reasoning):
        row["reasoning_tokens"] = int(reasoning)
    return row


class ProviderStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._lock = threading.Lock()

    def _migrate(self) -> None:
        """In-place upgrade of older databases: ALTER TABLE adds missing columns
        (SQLite has no ADD COLUMN IF NOT EXISTS).
        """
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(usage)")}
        if "cached_tokens" not in cols:
            self._conn.execute(
                "ALTER TABLE usage ADD COLUMN cached_tokens INTEGER NOT NULL DEFAULT 0"
            )
            self._conn.commit()
        for extra in ("reasoning_tokens", "cache_write_tokens"):
            if extra not in cols:
                self._conn.execute(
                    f"ALTER TABLE usage ADD COLUMN {extra} INTEGER NOT NULL DEFAULT 0"
                )
        self._conn.commit()
        pcols = {row[1] for row in self._conn.execute("PRAGMA table_info(providers)")}
        if "models_meta" not in pcols:
            self._conn.execute(
                "ALTER TABLE providers ADD COLUMN models_meta TEXT NOT NULL DEFAULT '{}'"
            )
            self._conn.commit()

    def upsert(self, p: dict[str, Any]) -> str:
        pid = p.get("id") or uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO providers (id, display_name, preset_id, base_url, api_format,"
                " models, models_meta, enabled, custom, created_ts, updated_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,"
                " base_url=excluded.base_url, api_format=excluded.api_format,"
                " models=excluded.models, models_meta=excluded.models_meta,"
                " enabled=excluded.enabled, updated_ts=excluded.updated_ts",
                (
                    pid,
                    p["display_name"],
                    p.get("preset_id", ""),
                    p["base_url"],
                    p["api_format"],
                    json.dumps(p.get("models", []), ensure_ascii=False),
                    json.dumps(p.get("models_meta", {}), ensure_ascii=False),
                    int(p.get("enabled", True)),
                    int(p.get("custom", False)),
                    now,
                    now,
                ),
            )
            self._conn.commit()
        return pid

    def get(self, pid: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {','.join(_COLS)} FROM providers WHERE id = ?", (pid,)
            ).fetchone()
        return _row(row) if row else None

    def list(self, *, include_disabled: bool = False) -> list[dict[str, Any]]:
        sql = f"SELECT {','.join(_COLS)} FROM providers"
        if not include_disabled:
            sql += " WHERE enabled = 1"
        with self._lock:
            rows = self._conn.execute(sql + " ORDER BY created_ts").fetchall()
        return [_row(r) for r in rows]

    def delete(self, pid: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM providers WHERE id = ?", (pid,))
            self._conn.commit()

    def record_usage(
        self,
        provider_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        *,
        cached_tokens: int = 0,
        reasoning_tokens: int = 0,
        cache_write_tokens: int = 0,
        caller: str = "",
        ok: bool = True,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO usage (ts, provider_id, model, caller, input_tokens,"
                " output_tokens, cached_tokens, ok, reasoning_tokens, cache_write_tokens)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    time.time(),
                    provider_id,
                    model,
                    caller,
                    input_tokens,
                    output_tokens,
                    cached_tokens,
                    int(ok),
                    reasoning_tokens,
                    cache_write_tokens,
                ),
            )
            self._conn.commit()

    def usage_stats(self, days: int = 30, *, recent_limit: int = 20) -> dict[str, Any]:
        """Aggregated usage for the usage page.

        Field contract (consumed by apps/web api/types/usage.ts and the
        agent-facing get_usage_stats tool):
        - input_tokens / output_tokens / calls and total_input_tokens /
          total_output_tokens: legacy flat totals (kept for existing consumers)
        - totals: total_tokens, input/output, prompt_cached_tokens (prompt
          tokens the provider served from its cache), prompt_uncached_tokens
          (= input - cached), completion_tokens (= output), calls
        - top: the model with the most tokens (absent when there is no usage)
        - by_model / by_provider: breakdowns carrying total_tokens
        - by_day: per local-calendar-day rows with the same token split plus a
          per-model breakdown (single-user local app: days follow the machine's
          local calendar, matching the heatmap's front-end layout)
        - heatmap: per-day call counts + intensity
        - recent: the newest calls first, capped at recent_limit
        Cost is not reported: prices are not persisted, so nothing is invented.
        """
        cutoff = time.time() - days * 86400
        with self._lock:
            total = self._conn.execute(
                "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0),"
                " COALESCE(SUM(cached_tokens),0), COUNT(*), COALESCE(SUM(reasoning_tokens),0),"
                " COALESCE(SUM(cache_write_tokens),0) FROM usage WHERE ts >= ?",
                (cutoff,),
            ).fetchone()
            by_model = [
                _split_row(
                    model=r[0],
                    input=r[1],
                    output=r[2],
                    cached=r[3],
                    calls=r[4],
                    reasoning=r[5],
                )
                for r in self._conn.execute(
                    "SELECT model, SUM(input_tokens), SUM(output_tokens), SUM(cached_tokens),"
                    " COUNT(*), SUM(reasoning_tokens) FROM usage"
                    " WHERE ts >= ? GROUP BY model ORDER BY 5 DESC",
                    (cutoff,),
                )
            ]
            by_provider = [
                _split_row(provider=r[0], input=r[1], output=r[2], cached=r[3], calls=r[4])
                for r in self._conn.execute(
                    "SELECT COALESCE(NULLIF(p.display_name, ''), u.provider_id),"
                    " SUM(u.input_tokens), SUM(u.output_tokens), SUM(u.cached_tokens), COUNT(*)"
                    " FROM usage u LEFT JOIN providers p ON p.id = u.provider_id"
                    " WHERE u.ts >= ? GROUP BY u.provider_id ORDER BY 5 DESC",
                    (cutoff,),
                )
            ]
            day_rows = self._conn.execute(
                "SELECT ts, model, input_tokens, output_tokens, cached_tokens,"
                " reasoning_tokens FROM usage WHERE ts >= ?",
                (cutoff,),
            ).fetchall()
            recent_rows = self._conn.execute(
                "SELECT u.id, u.ts, COALESCE(NULLIF(p.display_name, ''), u.provider_id), u.model,"
                " u.caller, u.input_tokens, u.output_tokens, u.cached_tokens, u.ok,"
                " u.reasoning_tokens"
                " FROM usage u LEFT JOIN providers p ON p.id = u.provider_id"
                " WHERE u.ts >= ? ORDER BY u.ts DESC, u.id DESC LIMIT ?",
                (cutoff, recent_limit),
            ).fetchall()

        days_acc: dict[str, dict[str, Any]] = {}
        for ts, model, row_input, row_output, row_cached, row_reasoning in day_rows:
            day = time.strftime("%Y-%m-%d", time.localtime(ts))
            bucket = days_acc.setdefault(
                day,
                {"input": 0, "output": 0, "cached": 0, "reasoning": 0, "calls": 0, "models": {}},
            )
            bucket["input"] += int(row_input)
            bucket["output"] += int(row_output)
            bucket["cached"] += int(row_cached)
            bucket["reasoning"] += int(row_reasoning)
            bucket["calls"] += 1
            per_model = bucket["models"].setdefault(model, {"input": 0, "output": 0, "calls": 0})
            per_model["input"] += int(row_input)
            per_model["output"] += int(row_output)
            per_model["calls"] += 1

        by_day: list[dict[str, Any]] = []
        for day, b in sorted(days_acc.items()):
            row = _split_row(
                date=day,
                input=b["input"],
                output=b["output"],
                cached=b["cached"],
                calls=b["calls"],
                reasoning=b["reasoning"],
            )
            row["by_model"] = [
                {
                    "model": model,
                    "input": m["input"],
                    "output": m["output"],
                    "total_tokens": m["input"] + m["output"],
                    "calls": m["calls"],
                }
                for model, m in sorted(
                    b["models"].items(), key=lambda kv: -(kv[1]["input"] + kv[1]["output"])
                )
            ]
            by_day.append(row)
        max_calls = max((d["calls"] for d in by_day), default=0)
        heatmap = [
            {"date": d["date"], "calls": d["calls"], "intensity": d["calls"] / max_calls}
            for d in by_day
            if max_calls > 0
        ]
        recent = [
            {
                "id": str(r[0]),
                "created_at": datetime.fromtimestamp(r[1], tz=UTC).isoformat(timespec="seconds"),
                "provider": r[2],
                "model": r[3],
                "agent_id": r[4],
                "prompt_cached_tokens": int(r[7]),
                "prompt_uncached_tokens": max(int(r[5]) - int(r[7]), 0),
                "completion_tokens": int(r[6]),
                "ok": bool(r[8]),
                **({"reasoning_tokens": int(r[9])} if int(r[9]) else {}),
            }
            for r in recent_rows
        ]
        totals = _split_row(
            input=total[0], output=total[1], cached=total[2], calls=total[3], reasoning=total[4]
        )
        out: dict[str, Any] = {
            "days": days,
            "input_tokens": int(total[0]),
            "output_tokens": int(total[1]),
            "calls": int(total[3]),
            "total_input_tokens": int(total[0]),
            "total_output_tokens": int(total[1]),
            "totals": totals,
            "by_model": by_model,
            "by_provider": by_provider,
            "by_day": by_day,
            "heatmap": heatmap,
            "recent": recent,
        }
        if by_model:
            top = max(by_model, key=lambda m: m["total_tokens"])
            out["top"] = {"model": top["model"], "total_tokens": top["total_tokens"]}
        return out

    def close(self) -> None:
        self._conn.close()


def _row(r: tuple) -> dict[str, Any]:
    d = dict(zip(_COLS, r))
    d["models"] = json.loads(d["models"])
    d["models_meta"] = json.loads(d["models_meta"])
    d["enabled"] = bool(d["enabled"])
    d["custom"] = bool(d["custom"])
    return d

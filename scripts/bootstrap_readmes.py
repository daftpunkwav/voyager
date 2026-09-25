"""Generate compact contract-compliant README skeletons for the packages
enumerated by the docs audit (T-22.8). One-shot bootstrap: content is
honest-but-compact per package; edit by hand afterwards.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

CONTENT: dict[str, str] = {
    "packages/notes/README.md": {
        "purpose": "Notes domain: markdown notes with versions, links, tags, trash, attachments, and view/batch operations.",
        "config": "notes.* settings keys (see settings.py): page size, editor behavior defaults.",
        "ext": "Add a capability by registering into `capabilities.py`'s registry (REST + agent bridge automatic); persistence lives in store/store_links.",
        "mx": "Tools: notes__create_note, notes__list_notes, notes__update_note, notes__link_note, ... Titles/content in plain text; results return note ids. Use for anything the user wants persisted as a document.",
        "limits": "Full-text search relies on the sources domain, not here; attachment previews are minimal.",
        "deferred": "Granular per-note ACLs; richer markdown extensions.",
    },
    "packages/sources/README.md": {
        "purpose": "Sources domain: import and search material from three modules — repo (git), doc (files), web (pages).",
        "config": "sources.* settings keys (github token, indexer concurrency).",
        "ext": "New importer = one module under modules/ with its own capabilities.py; shared URL safety comes from platform_webguard.",
        "mx": "Tools: sources__import_repo / save_url / search_documents / list_*. Import returns ids; search returns scored hits. Use before graph indexing.",
        "limits": "Web import follows SSRF-safe fetch only (no JS rendering); doc extraction covers common text formats.",
        "deferred": "More extractors (pdf tables); incremental re-index scheduling.",
    },
    "packages/graph/README.md": {
        "purpose": "Graph domain: build and query a knowledge graph (nodes/relations) from imported sources; code and L0 pipelines plus an AI guide.",
        "config": "graph.* settings keys (engine choice, queue concurrency).",
        "ext": "New pipeline = one directory under pipelines/ (they must not import each other); engine adapter in engines/.",
        "mx": "Tools: graph__enqueue_index, graph__query_graph, graph__expand_neighbors, graph__find_path, graph__cancel_index, ... Jobs are async (task.* events); queries return bounded subgraphs.",
        "limits": "C engine is vendored and platform-specific; layout is basic.",
        "deferred": "Incremental graph updates without full re-index.",
    },
    "packages/llm/README.md": {
        "purpose": "LLM domain: provider catalog, chat/stream/embedding calls, usage metering, price-table cost conversion.",
        "config": "llm.* settings: default provider/model, sampling, embedding model, price table (llm.pricing).",
        "ext": "New provider = catalog preset; new call type = one client module + one capability file under capabilities/.",
        "mx": "Tools: llm__complete / complete_stream / embed / get_usage_stats. Agents rarely call these directly — the harness transport does. complete fails soft with classified errors (rate limit / auth / overflow).",
        "limits": "Embeddings only on chat-format providers (OpenAI-compatible).",
        "deferred": "Per-purpose provider health tracking.",
    },
    "packages/settings/README.md": {
        "purpose": "Settings domain: REST/bridge access to the shared settings store plus theme keys.",
        "config": "Owns theme.* keys; all other modules register their defs into the same store.",
        "ext": "Nothing to extend here — register SettingDefs in your own module.",
        "mx": "Tools: settings__get_settings / set_setting. user_only keys reject agent actors at the settings layer.",
        "limits": "No schema versioning/migrations.",
        "deferred": "Per-key change permissions beyond user_only.",
    },
    "packages/office/README.md": {
        "purpose": "Office domain: create/read/update documents (doc) and decks (slides) as structured artifacts.",
        "config": "office.* settings keys (artifact workspace layout).",
        "ext": "New document family = one module under modules/ with capabilities.",
        "mx": "Tools (when the domain is enabled): office__create_doc / update_doc / ... Long-form editing is block-based; artifacts land under the workspace.",
        "limits": "Default-off; no WYSIWYG frontend (chat artifact cards only).",
        "deferred": "Rendering fidelity; spreadsheets.",
    },
    "packages/browser/README.md": {
        "purpose": "Browser domain: forward browser actions (navigate/click/type/read/screenshot) to an external browser host.",
        "config": "browser.* settings keys (host endpoint).",
        "ext": "New action = one capability in capabilities.py forwarding to the host protocol.",
        "mx": "Tools (when enabled): browser__navigate / click / type / read / screenshot. Slow, stateful — use when pages need JS or interaction, prefer web_fetch otherwise.",
        "limits": "Requires the external browser host; default-off.",
        "deferred": "Session pooling; multi-tab bookkeeping.",
    },
    "packages/code_exec/README.md": {
        "purpose": "Code execution domain: run snippets/files in runtimes (python/node/shell), docker-first with explicit host fallback.",
        "config": "code_exec.* settings: runtimes table, timeout, memory, network mode, host-fallback switch.",
        "ext": "New runtime = an entry in code_exec.runtimes.",
        "mx": "Tools (when enabled): code_exec__run_snippet / run_file (async JobRef; results via task.* events) and list_runtimes. Complements the agent's synchronous run_shell.",
        "limits": "Default-off (docker is environment-dependent); artifacts under workspace/sandbox.",
        "deferred": "Per-runtime resource quotas; output streaming.",
    },
    "packages/host/README.md": {
        "purpose": "Composition root (Runtime layer): scan domain cards, wire them, bridge capabilities to agent tools, mount the gateway, own the process lifespan.",
        "config": "host.* settings: domains whitelist, rate limits.",
        "ext": "A new domain appears by dropping a service.json package under packages/ — zero host changes (scan → wire → bridge → mount).",
        "mx": "Model-agnostic glue; the agent-facing experience is defined by the domains themselves.",
        "limits": "Single-process composition; multi-process split is a separate effort.",
        "deferred": "Per-domain startup health gates.",
    },
    "packages/gateway/README.md": {
        "purpose": "HTTP transport: capability mounting, chat SSE, uploads, activity feed, health, rate limiting, security headers.",
        "config": "gateway.* settings: rate limit per minute, SSE connection cap.",
        "ext": "New transport route = one router module under this package; business logic stays in domains.",
        "mx": "Model-agnostic transport; agents reach capabilities through the bridge, humans through REST.",
        "limits": "Single instance only (in-memory rate limiter/SSE state).",
        "deferred": "WebSocket transport.",
    },
    "packages/platform/webguard/README.md": {
        "purpose": "Shared URL safety guard: SSRF policy, DNS resolve-and-pin, per-hop redirect checks.",
        "config": "None (pure policy code).",
        "ext": "New guard = one more pure module; consumers translate ValueError into their error vocabulary.",
        "mx": "Model-agnostic security mechanism.",
        "limits": "fake-ip range (198.18.0.0/15) is allowed by policy (Clash-style proxies); TOCTOU remains for non-pinning consumers.",
        "deferred": "Optional full-pinning helper for the agent web tools.",
    },
    "agent/README.md": {
        "purpose": "The agent (Harness layer): event loop, master orchestration, subagents, context/memory, policy, tools, skills, plugins.",
        "config": "agent.* settings keys (see settings.py groups: rounds/context/fs/network/llm/memory/skills/outreach/execution).",
        "ext": "New tool = one file under tools/<group>/; new capability = one file under capabilities/<group>/ (same name, same engine — parity); new mode = one file under engine/modes/.",
        "mx": "This IS the model experience: tool descriptions, confirm dialogs, memory, context budgets.",
        "limits": "Single-process, single-user by design.",
        "deferred": "Multi-agent supervisor beyond the current tree (phase 20 scope).",
    },
    "agent/src/agent/runtime/README.md": {
        "purpose": "Runtime mechanisms: event loop, scheduler + durable queue, checkpoints, trajectory projection, meter/quota, trace spans, deadlines, loop guards.",
        "config": "agent.execution.* / agent.rounds.* / queue-related keys.",
        "ext": "One mechanism per file; add a sibling module, never grow an existing one across concerns.",
        "mx": "Model-agnostic machinery.",
        "limits": "In-process only.",
        "deferred": "Distributed queue backends.",
    },
    "agent/src/agent/memory/README.md": {
        "purpose": "Four memory kinds (profile/episodic/semantic/working) plus retrieval, distillation, and the episodic recorder.",
        "config": "agent.memory.* keys (retention, distill interval, context cards).",
        "ext": "New store = one sibling module wired through Memory; the recorder and distiller are the only writers besides tools.",
        "mx": "Model-agnostic; agents see memory via recall_memory/get_memory tools.",
        "limits": "Vector channel needs an embedder (llm.embedding_model); lexical otherwise.",
        "deferred": "Cross-session semantic consolidation.",
    },
    "agent/src/agent/policy/README.md": {
        "purpose": "Permission engine: network/fs/app/shell decisions plus approval memory.",
        "config": "agent.network.* / agent.fs.* / agent.app.* keys (hot-read).",
        "ext": "One dimension = one file (decide_* function); engine only dispatches.",
        "mx": "Model-agnostic; surfaces as L1 notify / L2 confirm dialogs.",
        "limits": "Approval matching is exact (tool, target); no path patterns.",
        "deferred": "Scoped wildcards for approvals.",
    },
    "agent/src/agent/master/README.md": {
        "purpose": "Orchestration: message arbitration, dispatch, task graph joins, blackboard, proactive outreach, sessions.",
        "config": "agent.outreach.* / agent.triggers.* keys.",
        "ext": "New orchestration concern = one sibling module (task_graph/blackboard/proactive pattern).",
        "mx": "Model-agnostic; agents experience it via spawn/board/reach_out surfaces.",
        "limits": "Tree-shaped dependencies only (no DAG engine).",
        "deferred": "Cross-session task coordination.",
    },
}


def main() -> None:
    for rel, spec in CONTENT.items():
        p = REPO / rel
        if p.is_file():
            text = p.read_text(encoding="utf-8")
            if all(sec in text for sec in ("## Purpose", "## Known Limitations")):
                print(f"skip (already compliant): {rel}")
                continue
        body = (
            f"# {p.parent.name if 'platform' not in rel else p.parent.parent.name + '/' + p.parent.name}\n\n"
            f"## Purpose\n\n{spec['purpose']}\n\n"
            f"## Configuration\n\n{spec['config']}\n\n"
            f"## Extension Points\n\n{spec['ext']}\n\n"
            f"## Model Experience\n\n{spec['mx']}\n\n"
            f"## Known Limitations\n\n{spec['limits']}\n\n"
            f"## Deferred Work\n\n{spec['deferred']}\n"
        )
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        print(f"wrote {rel}")


if __name__ == "__main__":
    main()

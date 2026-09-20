# sources

> Language: **English** | [简体中文](README.zh.md)

## Purpose

Sources domain: import and search material from three modules — repo (git), doc (files), web (pages).

## Configuration

sources.* settings keys (github token, indexer concurrency).

## Extension Points

New importer = one module under modules/ with its own capabilities.py; shared URL safety comes from platform_webguard.

## Model Experience

Tools: sources__import_repo / save_url / search_documents / list_*. Import returns ids; search returns scored hits. Use before graph indexing.

## Known Limitations

Web import follows SSRF-safe fetch only (no JS rendering); doc extraction covers common text formats.

## Deferred Work

More extractors (pdf tables); incremental re-index scheduling.

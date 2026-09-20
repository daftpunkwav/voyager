# platform/webguard

> Language: **English** | [简体中文](README.zh.md)

## Purpose

Shared URL safety guard: SSRF policy, DNS resolve-and-pin, per-hop redirect checks.

## Configuration

None (pure policy code).

## Extension Points

New guard = one more pure module; consumers translate ValueError into their error vocabulary.

## Model Experience

Model-agnostic security mechanism.

## Known Limitations

fake-ip range (198.18.0.0/15) is allowed by policy (Clash-style proxies); TOCTOU remains for non-pinning consumers.

## Deferred Work

Optional full-pinning helper for the agent web tools.

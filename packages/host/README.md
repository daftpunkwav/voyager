# host

> Language: **English** | [简体中文](README.zh.md)

## Purpose

Composition root (Runtime layer): scan domain cards, wire them, bridge capabilities to agent tools, mount the gateway, own the process lifespan.

## Configuration

host.* settings: domains whitelist, rate limits.

## Extension Points

A new domain appears by dropping a service.json package under packages/ — zero host changes (scan → wire → bridge → mount).

## Model Experience

Model-agnostic glue; the agent-facing experience is defined by the domains themselves.

## Known Limitations

Single-process composition; multi-process split is a separate effort.

## Deferred Work

Per-domain startup health gates.

# browser

## Purpose

Browser domain: forward browser actions (navigate/click/type/read/screenshot) to an external browser host.

## Configuration

browser.* settings keys (host endpoint).

## Extension Points

New action = one capability in capabilities.py forwarding to the host protocol.

## Model Experience

Tools (when enabled): browser__navigate / click / type / read / screenshot. Slow, stateful — use when pages need JS or interaction, prefer web_fetch otherwise.

## Known Limitations

Requires the external browser host; default-off.

## Deferred Work

Session pooling; multi-tab bookkeeping.

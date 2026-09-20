# definitions — persona data files (TOML)

One TOML per built-in persona; pure data, no code. `agent/personas/__init__.py` loads this directory (exported as `DEFINITIONS_DIR`) with `tomllib` into the frozen `Persona` dataclass from `agent/personas/base.py`, so adding or tuning a role never touches the loader. Legacy structural keys resolve to these files through the `ALIASES` table so persisted sessions migrate. Fields: `key`, `display_name`, `style`, `default_mode`, `tool_allow` (absent = untrimmed surface; a `prefix__*` entry is a prefix grant expanded against the current registry), `system_prompt`.

## Files

- orchestrator.toml — key `orchestrator`, display name Lucien: the resident persona that receives the user's messages first; no `tool_allow`; dispatch forces it to react
- recon.toml — Iris: search, fetching, and source reconnaissance; project quick looks
- explainer.toml — Elio: explaining and guided reading; default mode cot
- organizer.toml — Miyai: filing notes, resources, and knowledge into the library; `notes__*` prefix grant
- graph_guide.toml — Atlas: graph construction guidance and navigation; `graph__*` prefix grant

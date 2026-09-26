# agent.context — Context engineering

builder.py assembles the stable system head (rules → scoped rules → persona → skill index → profile → task brief → MCP instructions) and turn_context() renders the per-turn volatile block (memory cards, recall, subagent digests, current page, plan gate) as one trailing user row;
compressor.py compresses/prunes/rebuilds; loader.py is the on-demand
loader: skill/memory/page context (index resident, full text on demand).
The global rules source text lives in prompts/definitions/common.toml
(common.global_rules).
editor.py restructures the transcript via an LLM keep/summarize/drop plan and
governor.py owns the trigger threshold; backoff.py suppresses the planner
after repeated failures; prefix_watch.py logs request-head changes for
prefix-cache audits.

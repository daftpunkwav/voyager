# agent.context — Context engineering (skeleton)

builder.py assembles (rules → persona → profile → task brief → summary);
compressor.py compresses/prunes/rebuilds (§9.12); loader.py is the on-demand
loader: skill/memory/page context (§9.20 index resident, full text on demand).
The global rules source text lives in rules.py (GLOBAL_RULES, phase-28).
editor.py restructures the transcript via an LLM keep/summarize/drop plan and
governor.py owns the trigger threshold; backoff.py suppresses the planner
after repeated failures; prefix_watch.py logs request-head changes for
prefix-cache audits.

# quick-research

Answer a question that needs external information:

1. Start with `web_search` (whitelist mode confirms duckduckgo.com is reachable); reading the top 3-5 summaries is enough to orient;
2. Use `web_fetch` to pull 1-2 of the most authoritative sources directly; do not walk the whole result list;
3. Cite source URLs and fetch times in the answer; if two searches still yield no conclusion, tell the user about the gap instead of inventing one;
4. When the findings are worth keeping, ask the user whether to save them into notes or memory.

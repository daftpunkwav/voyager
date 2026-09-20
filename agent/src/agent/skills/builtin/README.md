# builtin — built-in skill packs shipped with the agent

One directory per skill, each holding a `SKILL.md` knowledge pack (workflow text, no code). `build.py` lists this directory first among the SkillLoader's sources, before the user's workspace skills directory; `skills/loader.py` keeps the name+description index resident in the system prompt and loads full text on demand. The `SKILL.md` files are written in Chinese.

## Contents

- explore-repo/ — understanding a repository: glob the top level, read the README, deliver a who/usage/core-modules summary
- import-to-graph/ — importing local material into the graph: sources import, index enqueue, progress tracking, spot checks with graph stats and queries
- organize-notes/ — turning raw material into notes: plan the steps with todowrite, create the note, link related notes, verify every item done
- quick-research/ — answering a question that needs external information: web_search to orient, web_fetch one or two authoritative sources, cite URLs, disclose gaps instead of inventing
- weekly-report/ — compiling the week's notes, library additions, and graph changes into a single note following the organize-notes conventions

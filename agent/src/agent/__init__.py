"""Agent Runtime: the resident process, the system's decision-maker.

It does not wait for user input: it watches the event stream and decides
autonomously whether to act or stay silent. The package layout is the
responsibility boundary: runtime / orchestrator / engine / mcp / sessions /
prompts / contracts / context / memory / personas / policy / skills / hooks /
tools / capabilities / plugins.

Run from the repository root: ``python -m agent.main`` (tests resolve via
the root pyproject pythonpath ["."]).
"""

__version__ = "0.1.0"

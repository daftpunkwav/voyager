"""Package anchor for agent tests.

Required: the member root directory `agent/` shares its name with the import
package, so pytest's importlib mode needs an __init__.py here to derive test
module names from `tests/` instead of building a namespace package over the
member root (which would shadow the installed `agent` package).
"""

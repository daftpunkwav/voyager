"""Shared URL safety guard (webguard): SSRF policy, DNS resolve-and-pin and
per-hop redirect checks — the single implementation behind the agent's web
tools and the sources domain's page importer.

Two consumers, two levels (both satisfy "a second implementation means split
the seam"): validate-only resolution for the agent's web_fetch/web_search,
full request pinning for sources save_url. Zero business vocabulary: errors
surface as ValueError/Exception subclasses the callers translate.
"""

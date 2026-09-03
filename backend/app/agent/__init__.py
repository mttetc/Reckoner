"""Agent layer (SPEC § 9): the LLM orchestrates tools; it is never the source of truth.

Every number the answer contains must come from a tool result (which carries provenance). The
runner audits the final text for numbers it cannot trace and reports them — SPEC § 13.1 says a
bare float is a failure, so we make it visible instead of hoping.
"""

"""Build corpus ingestion (SPEC § 7): permitted source → fetch → parse → validate → tag → store.

Source-agnostic. Game adapters provide fetchers (``app.games.<game>.sources``); this package
owns the policy (what may be fetched, how politely) and the pipeline (dedupe, validation, persist).
"""

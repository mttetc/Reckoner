"""Versioned knowledge + game-aware retrieval (SPEC § 6).

The game filter is a *correctness condition*: PoE and PoE2 share vocabulary with different
mechanics. Every retrieval call takes ``game`` as a required argument and filters on it before
any similarity ranking. The CI isolation test (tests/corpus/test_knowledge_isolation.py) proves it.
"""

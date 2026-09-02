"""Common, game-agnostic domain.

Rule (SPEC § 8, § 3.14): nothing in this package may reference a specific game or engine.
Adapters live in their own packages and depend on this one, never the reverse.
"""

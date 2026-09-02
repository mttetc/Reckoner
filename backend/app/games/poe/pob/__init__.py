"""Path of Building export format: code codec, XML parser, tree URL decoding, stat mapping.

Decision (docs/DECISIONS.md, ADR-001): the ``pobapi`` package was evaluated and dropped — it is
unmaintained since 2021 and fails to import under Python ≥ 3.12 through dead dependencies. The
export format itself is small and stable enough to own here.
"""

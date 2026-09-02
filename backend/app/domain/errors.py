class DomainError(Exception):
    """Base class for domain errors. Carries a stable machine code for the API layer."""

    code = "domain_error"


class InvalidBuildCode(DomainError):
    """The payload is not a build code this system can decode."""

    code = "invalid_build_code"


class UnsupportedGame(DomainError):
    code = "unsupported_game"


class EngineUnavailable(DomainError):
    """A deterministic calculation was requested but no engine can serve it (SPEC § 13.8)."""

    code = "engine_unavailable"


class ProvenanceViolation(DomainError):
    """A numeric value was produced without provenance (SPEC § 13.1: a bare float is a failure)."""

    code = "provenance_violation"

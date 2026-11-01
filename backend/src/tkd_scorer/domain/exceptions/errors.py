class DomainError(Exception):
    """Base domain error.

    code: optional machine-readable reason returned to clients next to the message (e.g. "match_closed"),
    so they can tell definitive rejections apart without parsing the text.
    """

    code: str | None = None

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class ValidationError(DomainError):
    """Raised when business validation fails."""


class NotFoundError(DomainError):
    """Raised when a domain object is not found."""


class ConflictError(DomainError):
    """Raised when a conflict is detected."""


class UnauthorizedError(DomainError):
    """Raised when security validation fails."""


class ForbiddenError(DomainError):
    """Raised when the caller is authenticated but not allowed to perform the action."""


class MatchClosedError(ConflictError):
    """Raised when a score event arrives for a match that was already closed (e.g. by the operator)."""

    code = "match_closed"

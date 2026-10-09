"""Domain exceptions for the Stock Technical Indicator API.

These are raised by service/repository layers and mapped centrally
to HTTP responses by exception_handlers in app/main.py.
"""


class DomainException(Exception):
    """Base class for all domain exceptions."""

    pass


class SymbolNotFoundException(DomainException):
    """Raised when no OHLC data exists for the requested symbol/date range."""

    pass


class InvalidDateRangeException(DomainException):
    """Raised when end date is before start date."""

    pass


class AccessDeniedException(DomainException):
    """Raised when the user's tier does not permit the requested indicator or date range."""

    def __init__(self, message: str = "Access denied"):
        self.message = message
        super().__init__(self.message)


class RateLimitExceededException(DomainException):
    """Raised when the user has exceeded their daily request quota."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("Rate limit exceeded for your tier")


class AuthenticationException(DomainException):
    """Raised when the API key is invalid or missing."""

    pass


class DependencyUnavailableException(DomainException):
    """A required database or quota dependency is temporarily unavailable."""


class ServiceBusyException(DomainException):
    """Analytical capacity is temporarily exhausted."""

"""Application exceptions."""


class PathCrawlerError(Exception):
    """Base class for clear user-facing errors."""


class ConfigurationError(PathCrawlerError):
    """Raised when configuration is invalid."""


class WordlistError(PathCrawlerError):
    """Raised when a wordlist cannot be loaded."""


class ReportError(PathCrawlerError):
    """Raised when a report cannot be written."""

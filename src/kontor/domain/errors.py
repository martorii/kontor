class KontorError(Exception):
    """Base class for domain errors."""


class UnknownFormatError(KontorError):
    """No registered parser recognizes the file."""


class MalformedFileError(KontorError):
    """The file matched a parser but its content is invalid."""

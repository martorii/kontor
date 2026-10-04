class KontorError(Exception):
    """Base class for domain errors."""


class UnknownFormatError(KontorError):
    """No registered parser recognizes the file."""


class MalformedFileError(KontorError):
    """The file matched a parser but its content is invalid."""


class DuplicateFileError(KontorError):
    """The same file (by hash) was already imported."""


class AccountNotFoundError(KontorError):
    """No account with the given id exists."""


class DuplicateIbanError(KontorError):
    """Another account already uses this IBAN."""


class RulesFileError(KontorError):
    """The rules file is missing, unreadable or invalid."""

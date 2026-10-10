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


class LLMUnavailableError(KontorError):
    """The LLM server cannot be reached."""


class LLMTimeoutError(KontorError):
    """The LLM did not answer within the timeout."""


class LLMInvalidOutputError(KontorError):
    """The LLM answer is unusable: bad JSON, a category outside the list, or no logprobs."""


class TransactionNotFoundError(KontorError):
    """No transaction with the given id exists."""


class InvalidCategoryError(KontorError):
    """The category does not exist or is not a subcategory (CONTRACT §5.6)."""


class InvalidDateRangeError(KontorError):
    """The start of a date range is after its end."""


class MixedCurrenciesError(KontorError):
    """The selected data spans several currencies; select one account."""

from collections.abc import Sequence

from kontor.adapters.parsers.dkb import DkbParser
from kontor.domain.errors import UnknownFormatError
from kontor.ports.parser import BankParser


class ParserRegistry:
    def __init__(self, parsers: Sequence[BankParser]) -> None:
        self._parsers = tuple(parsers)

    def detect(self, content: bytes) -> BankParser:
        for parser in self._parsers:
            if parser.detect(content):
                return parser
        raise UnknownFormatError("file format not recognized by any parser")

    def get(self, format_name: str) -> BankParser:
        for parser in self._parsers:
            if parser.format_name == format_name:
                return parser
        raise UnknownFormatError(f"no parser registered for format {format_name!r}")


def default_registry() -> ParserRegistry:
    return ParserRegistry([DkbParser()])

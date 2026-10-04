import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError

from kontor.adapters.rules.schema import RulesFileSchema
from kontor.domain.errors import RulesFileError
from kontor.domain.rules import RulesConfig


def _location(loc: tuple[int | str, ...]) -> str:
    return ".".join(str(part) for part in loc) or "(file)"


class YamlRulesSource:
    """Reads the rules YAML. Kontor never writes to this file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> RulesConfig:
        try:
            content = self._path.read_bytes()
        except OSError as exc:
            raise RulesFileError(f"cannot read rules file {self._path}: {exc.strerror}") from exc

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise RulesFileError(f"{self._path}: invalid YAML: {exc}") from exc

        try:
            schema = RulesFileSchema.model_validate(data)
        except ValidationError as exc:
            problems = "; ".join(
                f"{_location(error['loc'])}: {error['msg']}" for error in exc.errors()
            )
            raise RulesFileError(f"{self._path}: invalid rules: {problems}") from exc

        categories, rules = schema.to_domain()
        return RulesConfig(
            categories=categories,
            rules=rules,
            file_hash=hashlib.sha256(content).hexdigest(),
        )

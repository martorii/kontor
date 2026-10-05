import ast
from pathlib import Path

UI = Path(__file__).resolve().parents[3] / "ui"
FORBIDDEN = {"kontor", "sqlalchemy", "psycopg", "psycopg2", "alembic"}


def test_ui_has_no_database_or_backend_imports() -> None:
    """The UI is a thin client: HTTP only (CONTRACT §2.3)."""
    offenders = []
    for path in UI.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            offenders += [
                f"{path.relative_to(UI)}: {m}" for m in modules if m.split(".")[0] in FORBIDDEN
            ]
    assert offenders == []

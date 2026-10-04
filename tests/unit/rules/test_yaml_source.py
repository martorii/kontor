from pathlib import Path
from textwrap import dedent

import pytest

from kontor.adapters.rules.yaml_source import YamlRulesSource
from kontor.application.rules_holder import RulesHolder
from kontor.domain.errors import RulesFileError

ROOT = Path(__file__).resolve().parents[3]

VALID = """\
categories:
  - {slug: food, name: Food, kind: expense}
  - {slug: food.groceries, name: Groceries, parent: food}
rules:
  - {id: rewe, category: food.groceries, field: counterparty, match: REWE}
"""


def write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "rules.yaml"
    path.write_text(dedent(content))
    return path


def load(tmp_path: Path, content: str) -> None:
    YamlRulesSource(write(tmp_path, content)).load()


def test_example_file_is_valid() -> None:
    config = YamlRulesSource(ROOT / "config" / "rules.example.yaml").load()

    slugs = {c.slug for c in config.categories}
    assert len(slugs) == len(config.categories)
    assert "kids.daycare" in slugs
    assert all(r.category_slug in slugs for r in config.rules)


def test_valid_file_maps_to_domain(tmp_path: Path) -> None:
    config = YamlRulesSource(write(tmp_path, VALID)).load()

    food, groceries = config.categories
    assert (food.slug, food.kind, food.parent_slug) == ("food", "expense", None)
    assert (groceries.slug, groceries.kind, groceries.parent_slug) == (
        "food.groceries",
        None,
        "food",
    )
    (rule,) = config.rules
    assert (rule.id, rule.field, rule.pattern, rule.match_type) == (
        "rewe",
        "counterparty",
        "REWE",
        "contains",
    )
    assert len(config.file_hash) == 64


def test_file_hash_changes_with_content(tmp_path: Path) -> None:
    first = YamlRulesSource(write(tmp_path, VALID)).load().file_hash
    second = YamlRulesSource(write(tmp_path, VALID + "# edit\n")).load().file_hash
    assert first != second


def test_missing_file_has_readable_error(tmp_path: Path) -> None:
    with pytest.raises(RulesFileError, match="cannot read rules file"):
        YamlRulesSource(tmp_path / "nope.yaml").load()


def test_invalid_yaml_syntax(tmp_path: Path) -> None:
    with pytest.raises(RulesFileError, match="invalid YAML"):
        load(tmp_path, "categories: [unclosed\n")


def test_wrong_shape_names_the_field(tmp_path: Path) -> None:
    with pytest.raises(RulesFileError, match=r"categories\.0\.name"):
        load(tmp_path, "categories:\n  - {slug: food, kind: expense}\n")


def test_empty_file(tmp_path: Path) -> None:
    with pytest.raises(RulesFileError, match="invalid rules"):
        load(tmp_path, "")


def test_unknown_key_rejected(tmp_path: Path) -> None:
    with pytest.raises(RulesFileError, match="bogus"):
        load(tmp_path, VALID + "bogus: 1\n")


def test_duplicate_slug_rejected(tmp_path: Path) -> None:
    content = VALID.replace("rules:", "  - {slug: food, name: Again, kind: expense}\nrules:")
    with pytest.raises(RulesFileError, match="duplicate category slug: food"):
        load(tmp_path, content)


def test_missing_parent_rejected(tmp_path: Path) -> None:
    content = """\
        categories:
          - {slug: food.groceries, name: Groceries, parent: food}
        """
    with pytest.raises(RulesFileError, match="parent 'food' does not exist"):
        load(tmp_path, content)


def test_three_levels_rejected(tmp_path: Path) -> None:
    content = VALID.replace(
        "rules:", "  - {slug: food.groceries.bio, name: Bio, parent: food.groceries}\nrules:"
    )
    with pytest.raises(RulesFileError):
        load(tmp_path, content)


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("{slug: x, name: X}", "needs a kind"),
        ("{slug: x, name: X, kind: nonsense}", "kind"),
        ("{slug: x.y, name: X, kind: expense}", "must not contain a dot"),
        ("{slug: food.a, name: A, parent: food, kind: expense}", "must not have a kind"),
        ("{slug: other.a, name: A, parent: food}", "must start with 'food.'"),
        ("{slug: Bad Slug, name: X, kind: expense}", "slug"),
    ],
)
def test_invalid_categories(tmp_path: Path, line: str, message: str) -> None:
    content = f"categories:\n  - {{slug: food, name: Food, kind: expense}}\n  - {line}\n"
    with pytest.raises(RulesFileError, match=message):
        load(tmp_path, content)


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        ("{id: r, category: nope.x, field: purpose, match: a}", "unknown category"),
        ("{id: r, category: food, field: purpose, match: a}", "not a subcategory"),
        ("{id: r, category: food.groceries, field: amount, match: a}", "field"),
        (
            "{id: r, category: food.groceries, field: purpose, match: '('," + " type: regex}",
            "regular expression",
        ),
        ("{id: rewe, category: food.groceries, field: purpose, match: a}", "duplicate rule id"),
        (
            "{id: r, category: food.groceries, field: purpose, match: a,"
            " when: {amount_min: 5, amount_max: 1}}",
            "must not exceed",
        ),
        (
            "{id: r, category: food.groceries, field: purpose, match: a,"
            " when: {amount_sign: zero}}",
            "amount_sign",
        ),
    ],
)
def test_invalid_rules(tmp_path: Path, rule: str, message: str) -> None:
    with pytest.raises(RulesFileError, match=message):
        load(tmp_path, VALID + f"  - {rule}\n")


def test_failed_reload_keeps_previous_rules(tmp_path: Path) -> None:
    path = write(tmp_path, VALID)
    holder = RulesHolder(YamlRulesSource(path))
    first = holder.load()

    path.write_text("categories: [broken\n")
    with pytest.raises(RulesFileError):
        holder.reload()

    assert holder.current is first


def test_successful_reload_replaces_rules(tmp_path: Path) -> None:
    path = write(tmp_path, VALID)
    holder = RulesHolder(YamlRulesSource(path))
    first = holder.load()

    path.write_text(VALID.replace("REWE", "EDEKA"))

    assert holder.reload() is not first
    assert holder.current.rules[0].pattern == "EDEKA"


def test_current_before_load_raises(tmp_path: Path) -> None:
    with pytest.raises(RulesFileError):
        RulesHolder(YamlRulesSource(tmp_path / "x.yaml")).current  # noqa: B018

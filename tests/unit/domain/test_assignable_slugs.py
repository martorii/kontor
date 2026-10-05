from kontor.domain.rules import CategoryDef, assignable_slugs


def test_only_subcategories_are_assignable() -> None:
    categories = [
        CategoryDef("food", "Food", None, "expense"),
        CategoryDef("food.groceries", "Groceries", "food", None),
        CategoryDef("income", "Income", None, "income"),
    ]
    assert assignable_slugs(categories) == ("food.groceries",)

from kontor.domain.rules import CategoryDef, leaf_slugs


def test_leaf_slugs_are_the_categories_without_subcategories() -> None:
    categories = [
        CategoryDef("food", "Food", None, "expense"),
        CategoryDef("food.groceries", "Groceries", "food", None),
        CategoryDef("income", "Income", None, "income"),
    ]
    assert leaf_slugs(categories) == ("food.groceries", "income")

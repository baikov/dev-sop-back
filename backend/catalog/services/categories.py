from django.db.models import Q
from django.db.models.query import QuerySet

# from loguru import logger as log
from rest_framework.exceptions import NotFound

from backend.catalog.models import (
    Category,
    Product,
    ProductProperty,
    ProductPropertyValue,
)
from backend.utils.custom import get_object_or_None


def get_category_list() -> QuerySet:
    """
    Возвращает список объектов. Реализована фильтрация.
    """
    qs = Category.objects.filter(is_published=True)
    return qs


def get_root_categories() -> QuerySet:
    """
    Возвращает список объектов. Реализована фильтрация.
    """
    qs = Category.get_root_nodes().filter(is_published=True)
    return qs


def get_children_categories(slug: str) -> QuerySet:
    category = get_object_or_None(Category, slug=slug)
    if category is None:
        raise NotFound(f"Категория slug={slug} не существует")

    return category.get_children().filter(is_published=True)


def get_category_subtree_ids_list(slug: str) -> list:
    category = get_object_or_None(Category, slug=slug)
    if category is None:
        raise NotFound(f"Категория slug={slug} не существует")
    subtree = (
        category.get_descendants()
        .filter(is_published=True)
        .values_list("id", flat=True)
    )
    return list(subtree)


def add_category_products_properties(category: Category) -> None:
    """
    Создает записи таблицы ProductPropertyValue (Свойство - Значение) для всех продуктов
    категории, если она является главной для этих продуктов
    """

    products = Product.objects.filter(
        product_categories__category=category, product_categories__is_primary=True
    )
    if products is None:
        return
    for product in products:
        properties = category.product_properties.difference(product.properties.all())
        for property in properties:
            product.properties_through.create(property=property)


def get_unique_property_values(
    category: Category, property: ProductProperty
) -> list[str]:
    """
    Возвращает уникальные значения свойства для всех продуктов категории
    и ее подкатегорий
    """

    digit_values: list[int | float] = []
    non_digit_values = []
    categories = []
    categories.append(category)
    if not category.is_leaf():
        categories.extend(category.get_descendants().filter(is_published=True))

    property_values = (
        ProductPropertyValue.objects.select_related(
            "product__product_categories__category"
        )
        .prefetch_related("product__product_categories")
        .filter(
            property=property,
            product__product_categories__category__in=categories,
        )
        .exclude(Q(value=None) | Q(value=""))
        .values_list("value", flat=True)
        .distinct()
    )

    for value in property_values:
        try:
            digit_values.append(int(value))
        except ValueError:
            try:
                digit_values.append(float(value.replace(",", ".")))
            except ValueError:
                non_digit_values.append(value)

    result = sorted(digit_values) + non_digit_values
    return [str(value) for value in result]

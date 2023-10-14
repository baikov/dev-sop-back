from django.db.models import CharField, F, FloatField, Func, OuterRef, Subquery, Value
from django.db.models.functions import Cast
from django.db.models.query import QuerySet
from rest_framework.exceptions import NotFound

from backend.catalog.filters import ProductFilter
from backend.catalog.models import Category, Product, ProductPropertyValue
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


def get_category_product_list(slug: str, filters: dict = {}) -> QuerySet:
    # filters = filters or {}

    category = get_object_or_None(Category, slug=slug)
    if category is None:
        raise NotFound(f"Категория slug={slug} не существует")

    qs = category.products.filter(is_published=True)
    # Если категория является родительской - сформируем список продуктов
    # из дочерних категорий
    if not category.is_leaf():
        leafs_categories = category.get_descendants().filter(
            is_published=True, numchild=0
        )
        for leaf_category in leafs_categories:
            qs = qs.union(
                leaf_category.products.filter(is_published=True, in_stock=True)
            )
    else:
        first_property = category.product_properties.exclude(
            code__in=[
                "gost",
                "marka-stali",
                "poverkhnost",
                "occvet",
                "ves-metra",
                "ves-shtuki",
                "tolshina-stenki",
            ]
        ).first()
        if first_property:
            qs = qs.annotate(
                property_value=Cast(
                    Subquery(
                        ProductPropertyValue.objects.filter(
                            property_id=first_property.id, product_id=OuterRef("pk")
                        ).values(
                            property_value=Func(
                                F("value"),
                                Value(","),
                                Value("."),
                                function="REPLACE",
                                output_field=CharField(),
                            )
                        )[
                            :1
                        ]
                    ),
                    output_field=FloatField(),
                ),
                # Если нужно рассчитать цены на лету
                # meter_weight=Cast(
                #     Subquery(
                #         ProductPropertyValue.objects.filter(
                #             property__code="ves-metra", product_id=OuterRef("pk")
                #         ).values(
                #             property_value=Func(
                #                 F("value"),
                #                 Value(","),
                #                 Value("."),
                #                 function="REPLACE",
                #                 output_field=CharField(),
                #             )
                #         )[
                #             :1
                #         ]
                #     ),
                #     output_field=FloatField(),
                # ),
                # dlina=Cast(
                #     Subquery(
                #         ProductPropertyValue.objects.filter(
                #             property__code="dlina", product_id=OuterRef("pk")
                #         ).values(property_value=F("value"))[:1]
                #     ),
                #     output_field=CharField(),
                # ),
            ).order_by("-in_stock", "property_value")
    return ProductFilter(filters, qs).qs


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

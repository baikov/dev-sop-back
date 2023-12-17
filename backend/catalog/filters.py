from django.db.models import (
    CharField,
    F,
    FloatField,
    Func,
    OuterRef,
    Subquery,
    Value,
)
from django.db.models.functions import Cast
from django_filters import rest_framework as filters
from loguru import logger as log

from backend.catalog.models import Category, Product, ProductPropertyValue
from backend.catalog.services.categories import get_category_subtree_ids_list
from backend.utils.custom import get_object_or_None


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class PropertiesOrderingFilter(filters.OrderingFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra["choices"] += [
            ("diametr", "Diameter"),
            ("-diametr", "Diameter (descending)"),
            ("dlina", "Length"),
            ("-dlina", "Length (descending)"),
        ]

    def filter(self, qs, value):
        # OrderingFilter is CSV-based, so `value` is a list
        log.debug("qs: {}", qs)
        log.debug("value: {}", value)
        if value is None:
            return super().filter(qs, value)
        if any(v in ["diametr", "-diametr", "dlina", "-dlina"] for v in value):
            qs = qs.annotate(
                prop=Cast(
                    Subquery(
                        ProductPropertyValue.objects.filter(
                            property__code=value[0].replace("-", ""),
                            product_id=OuterRef("pk"),
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
            )
            log.debug("qs: {}", qs)
            return qs.order_by(
                "-prop" if value[0].startswith("-") else "prop"
            )  # ("-in_stock", value[0])

        return super().filter(qs, value)


class ProductFilter(filters.FilterSet):
    # min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    # max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    gost = filters.CharFilter(method="params_filter")
    diametr = filters.CharFilter(method="params_filter")
    tolshina_stenki = filters.CharFilter(method="params_filter")
    marka_stali = filters.CharFilter(method="params_filter")
    dlina = filters.CharFilter(method="params_filter")
    category = filters.CharFilter(method="category_filter")

    sort = PropertiesOrderingFilter()

    class Meta:
        model = Product
        fields = (
            "name",
            "gost",
            "diametr",
            "tolshina_stenki",
            "category",
            "marka_stali",
            "dlina",
        )

    def params_filter(self, queryset, name, value):
        property_values = ProductPropertyValue.objects.filter(
            property__code=name, value=value
        )
        return queryset.filter(properties_through__in=property_values)

    def category_filter(self, queryset, name, value):
        category = get_object_or_None(Category, slug=value)
        if category is None:
            raise ValueError(f"Категория slug={value} не существует")
        category_ids = get_category_subtree_ids_list(value) + [category.id]
        return queryset.filter(categories__id__in=category_ids)

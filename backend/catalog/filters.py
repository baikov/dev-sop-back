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

from backend.catalog.models import Category, Product, ProductProperty, ProductPropertyValue
from backend.catalog.services.categories import get_category_subtree_ids_list
from backend.utils.custom import get_object_or_None


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class PropertiesOrderingFilter(filters.OrderingFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ! Error in migration on clean db. Probably because the relations are not created yet
        # ! django.db.utils.ProgrammingError: relation "catalog_product_property" does not exist
        # sortable_props = ProductProperty.objects.values("code", "name")
        # extra_choices = [(prop["code"], prop["name"]) for prop in sortable_props] + [
        #     ("-" + prop["code"], prop["name"] + " (descending)") for prop in sortable_props
        # ]

        # self.extra["choices"] += extra_choices

    def filter(self, qs, value):
        # OrderingFilter is CSV-based, so `value` is a list
        if value is None:
            return super().filter(qs, value)
        sortable_props = list(ProductProperty.objects.filter(is_sortable=True).values_list("code", flat=True))

        if any(v in sortable_props + [f"-{prop}" for prop in sortable_props] for v in value):
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
                        )[:1]
                    ),
                    output_field=FloatField(),
                ),
            )
            return qs.order_by("-prop" if value[0].startswith("-") else "prop")  # ("-in_stock", value[0])
        else:
            return qs


class ProductFilter(filters.FilterSet):
    # min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    # max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    gost = filters.CharFilter(method="params_filter")
    diametr = filters.CharFilter(method="params_filter")
    tolshina_stenki = filters.CharFilter(method="params_filter")
    marka_stali = filters.CharFilter(method="params_filter")
    dlina = filters.CharFilter(method="params_filter")
    category = filters.CharFilter(method="category_filter")
    vysota_h = filters.CharFilter(method="params_filter")
    shirina_b = filters.CharFilter(method="params_filter")
    name = filters.CharFilter(lookup_expr="icontains")

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
            "vysota_h",
            "shirina_b",
            "dlina",
        )

    def params_filter(self, queryset, name, value):
        property_values = ProductPropertyValue.objects.filter(property__code=name, value=value.replace(".", ","))
        return queryset.filter(properties_through__in=property_values)

    def category_filter(self, queryset, name, value):
        category = get_object_or_None(Category, slug=value)
        if category is None:
            raise ValueError(f"Категория slug={value} не существует")
        category_ids = get_category_subtree_ids_list(value) + [category.id]
        return queryset.filter(categories__id__in=category_ids)

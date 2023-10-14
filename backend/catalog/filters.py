from django_filters import rest_framework as filters

from backend.catalog.models import Product, ProductPropertyValue


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class ProductFilter(filters.FilterSet):
    # min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    # max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    gost = filters.CharFilter(method="params_filter")
    diametr = filters.CharFilter(method="params_filter")
    thickness = filters.CharFilter(method="params_filter")

    class Meta:
        model = Product
        fields = ("name", "gost", "diametr", "thickness")

    def params_filter(self, queryset, name, value):
        property_values = ProductPropertyValue.objects.filter(
            property__slug=name, value__icontains=value
        )
        return queryset.filter(properties_through__in=property_values)

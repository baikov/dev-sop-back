import math

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from backend.catalog.services.categories import (
    get_children_categories,
    get_unique_property_values,
)
from backend.utils.custom import create_breadcrumbs


class SEOSerializer(serializers.Serializer):
    slug = serializers.CharField(read_only=True)
    seo_title = serializers.CharField(read_only=True)
    seo_description = serializers.CharField(read_only=True)
    h1 = serializers.CharField(read_only=True)
    is_index = serializers.BooleanField(read_only=True)
    is_follow = serializers.BooleanField(read_only=True)


class SEOMixin(serializers.Serializer):
    seo = serializers.SerializerMethodField()

    def get_seo(self, obj):
        seo_fields = {
            "seo_title": obj.seo_title,
            "seo_description": obj.seo_description,
            "h1": obj.h1,
            "is_index": obj.is_index,
            "is_follow": obj.is_follow,
        }
        return SEOSerializer(seo_fields).data


class ProductFilterSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    # price = serializers.DecimalField(required=False, max_digits=20, decimal_places=2)
    gost = serializers.CharField(required=False)
    diametr = serializers.CharField(required=False)
    thickness = serializers.CharField(required=False)


class ProductPropertySerializer(serializers.Serializer):
    id = serializers.ReadOnlyField(source="property.id")
    name = serializers.ReadOnlyField(source="property.name")
    code = serializers.ReadOnlyField(source="property.code")
    units = serializers.ReadOnlyField(source="property.units")
    is_display_in_list = serializers.BooleanField(
        read_only=True, source="property.is_display_in_list"
    )
    value = serializers.ReadOnlyField()
    ordering = serializers.ReadOnlyField(source="property.ordering")


class CategoryPropertySerializer(serializers.Serializer):
    id = serializers.ReadOnlyField(read_only=True)
    name = serializers.ReadOnlyField(read_only=True)
    code = serializers.ReadOnlyField(read_only=True)
    is_display_in_list = serializers.BooleanField(read_only=True)
    ordering = serializers.ReadOnlyField(read_only=True)
    values = serializers.SerializerMethodField(read_only=True)

    def get_values(self, obj):
        category = self.context["category"]
        values = get_unique_property_values(category, obj)
        return values


class ProductListOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    ton_price_with_coef = serializers.SerializerMethodField(read_only=True)
    unit_price_with_coef = serializers.SerializerMethodField(read_only=True)
    meter_price_with_coef = serializers.SerializerMethodField(read_only=True)
    properties = serializers.SerializerMethodField(read_only=True)
    in_stock = serializers.SerializerMethodField(read_only=True)

    def get_in_stock(self, obj):
        return obj.always_in_stock if obj.always_in_stock else obj.in_stock

    def get_unit_price_with_coef(self, obj):
        primary_category = obj.categories.filter(
            product_categories__is_primary=True
        ).first()
        unit_price = obj.custom_unit_price or obj.unit_price
        return math.ceil(unit_price * primary_category.price_coefficient)

    def get_meter_price_with_coef(self, obj):
        primary_category = obj.categories.filter(
            product_categories__is_primary=True
        ).first()
        meter_price = obj.custom_meter_price or obj.meter_price
        return math.ceil(meter_price * primary_category.price_coefficient)

    def get_ton_price_with_coef(self, obj):
        primary_category = obj.categories.filter(
            product_categories__is_primary=True
        ).first()
        ton_price = obj.custom_ton_price if obj.custom_ton_price else obj.ton_price
        if not ton_price:
            return 0
        return (round(ton_price * primary_category.price_coefficient) // 100 + 1) * 100

    @extend_schema_field(ProductPropertySerializer(many=True))
    def get_properties(self, obj):
        return ProductPropertySerializer(
            obj.properties_through.filter(property__is_display_in_list=True), many=True
        ).data


class ProductDetailOutputSerializer(ProductListOutputSerializer, SEOMixin):
    category = serializers.SerializerMethodField(read_only=True)
    description = serializers.CharField()
    breadcrumbs = serializers.SerializerMethodField(read_only=True)
    properties = ProductPropertySerializer(
        read_only=True, many=True, source="properties_through"
    )  # type: ignore

    def get_category(self, obj):
        return obj.categories.filter(product_categories__is_primary=True).first().name

    def get_breadcrumbs(self, obj):
        category = obj.categories.filter(product_categories__is_primary=True).first()
        last_item = {
            "level": category.depth + 1,
            "name": obj.name,
            "href": f"/product/{obj.slug}",
            "disabled": True,
        }
        breadcrumbs = create_breadcrumbs(category, disable_last=False)
        breadcrumbs.append(last_item)
        return breadcrumbs


class CategoryFilterSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)


class CategoryListOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    image = serializers.ImageField(read_only=True, use_url=False)
    # products_count = serializers.IntegerField(read_only=True)


class CategoryDetailOutputSerializer(CategoryListOutputSerializer, SEOMixin):
    parent = serializers.IntegerField(read_only=True)  # type: ignore
    description = serializers.CharField(read_only=True)
    breadcrumbs = serializers.SerializerMethodField(read_only=True)
    # product_properties = CategoryPropertySerializer(many=True)
    product_properties = serializers.SerializerMethodField()
    subcategories = serializers.SerializerMethodField()

    def get_breadcrumbs(self, obj):
        breadcrumbs = create_breadcrumbs(obj)
        return breadcrumbs

    def get_product_properties(self, obj):
        return CategoryPropertySerializer(
            obj.product_properties.filter(is_display_in_list=True),
            many=True,
            context={"category": obj},
        ).data

    def get_subcategories(self, obj):
        children = get_children_categories(obj.slug)
        return CategoryListOutputSerializer(children, many=True).data

    class Meta:
        lookup_field = "slug"
        extra_kwargs = {"url": {"lookup_field": "slug"}}


class CatalogLeftMenuSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    depth = serializers.IntegerField(read_only=True)
    slug = serializers.CharField(read_only=True)
    submenu = serializers.SerializerMethodField(read_only=True)
    image = serializers.ImageField(read_only=True, use_url=False)

    def get_submenu(self, obj):
        submenu = get_children_categories(obj.slug)
        return CatalogLeftMenuSerializer(
            submenu,
            many=True,
            required=False,
        ).data

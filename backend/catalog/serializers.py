import math

from django.conf import settings
from django.db.models import Max, Min
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from backend.catalog.models import Category, Document, FormSubmission, Product
from backend.catalog.services.categories import (
    get_children_categories,
    get_unique_property_values,
)
from backend.catalog.services.products import (
    get_img_path,
    get_related_products,
    get_same_category_products,
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
    is_display_in_list = serializers.BooleanField(read_only=True, source="property.is_display_in_list")
    value = serializers.ReadOnlyField()
    ordering = serializers.ReadOnlyField(source="property.ordering")
    is_sortable = serializers.BooleanField(source="property.is_sortable")


class CategoryPropertySerializer(serializers.Serializer):
    id = serializers.ReadOnlyField(read_only=True)
    name = serializers.ReadOnlyField(read_only=True)
    code = serializers.ReadOnlyField(read_only=True)
    is_display_in_list = serializers.BooleanField(read_only=True)
    ordering = serializers.ReadOnlyField(read_only=True)
    values = serializers.SerializerMethodField(read_only=True)
    is_sortable = serializers.BooleanField(read_only=True)

    def get_values(self, obj):
        category = self.context["category"]
        values = get_unique_property_values(category, obj)
        return values


class CategoryYMLSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    parent_id = serializers.SerializerMethodField(read_only=True)

    def get_parent_id(self, obj: Category):
        return obj.get_parent().id if obj.get_parent() else 0


class ProductYMLSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    # category_id = serializers.SerializerMethodField(read_only=True)
    category_id = serializers.IntegerField(read_only=True, source="prim")
    price = serializers.SerializerMethodField(read_only=True)
    picture = serializers.SerializerMethodField(read_only=True)
    description = serializers.SerializerMethodField(read_only=True)

    def get_picture(self, obj) -> str:
        # cat = obj.categories.filter(product_categories__is_primary=True).first()
        try:
            cat = Category.objects.get(pk=obj.prim)
        except Category.DoesNotExist:
            cat = None
        return (
            obj.image.url
            if obj.image
            else cat.product_image.url
            if cat and cat.product_image
            else cat.image.url
            if cat
            else ""
        )

    def get_price(self, obj) -> int:
        # primary_category = obj.categories.filter(product_categories__is_primary=True).first()
        try:
            primary_category = Category.objects.get(pk=obj.prim)
        except Category.DoesNotExist:
            return 0
        ton_price = obj.custom_ton_price or obj.ton_price
        unit_price = obj.custom_unit_price or obj.unit_price
        meter_price = obj.custom_meter_price or obj.meter_price
        if primary_category:
            ton_price_coef = (round(ton_price * primary_category.price_coefficient) // 100 + 1) * 100
            unit_price_coef = math.ceil(unit_price * primary_category.price_coefficient)
            meter_price_coef = math.ceil(meter_price * primary_category.price_coefficient)

            return ton_price_coef or meter_price_coef or unit_price_coef or 0
        return 0

    # def get_category_id(self, obj: Product) -> int:
    #     cat = obj.categories.filter(product_categories__is_primary=True).first()
    #     return cat.id if cat else 0

    def get_description(self, obj: Product) -> str:
        default_desc = (
            f"{obj.name} от ООО «Спецоптторг» по выгодным ценам со склада в Нижнем Новгороде. Доставка по области."
        )
        return obj.description or obj.seo_description or default_desc


class YMLSerializer(serializers.Serializer):
    categories = CategoryYMLSerializer(many=True)
    products = ProductYMLSerializer(many=True)


class ProductListOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    ton_price_with_coef = serializers.SerializerMethodField(read_only=True)
    unit_price_with_coef = serializers.SerializerMethodField(read_only=True)
    meter_price_with_coef = serializers.SerializerMethodField(read_only=True)
    properties = serializers.SerializerMethodField(read_only=True)
    in_stock = serializers.SerializerMethodField(read_only=True)

    def get_in_stock(self, obj: Product):
        return obj.always_in_stock if obj.always_in_stock else obj.in_stock

    def get_unit_price_with_coef(self, obj: Product) -> int:
        primary_category = obj.categories.filter(product_categories__is_primary=True).first()
        unit_price = obj.custom_unit_price or obj.unit_price
        if primary_category:
            return math.ceil(unit_price * primary_category.price_coefficient)
        return 0

    def get_meter_price_with_coef(self, obj: Product) -> int:
        primary_category = obj.categories.filter(product_categories__is_primary=True).first()
        meter_price = obj.custom_meter_price or obj.meter_price
        if primary_category:
            return math.ceil(meter_price * primary_category.price_coefficient)
        return 0

    def get_ton_price_with_coef(self, obj: Product) -> int:
        primary_category = obj.categories.filter(product_categories__is_primary=True).first()
        ton_price = obj.custom_ton_price if obj.custom_ton_price else obj.ton_price
        if not ton_price:
            return 0
        if primary_category:
            return (round(ton_price * primary_category.price_coefficient) // 100 + 1) * 100
        return 0

    @extend_schema_field(ProductPropertySerializer(many=True))
    def get_properties(self, obj):
        return ProductPropertySerializer(
            obj.properties_through.filter(property__is_display_in_list=True), many=True
        ).data


class NestedDocumentSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True, source="document.id")
    title = serializers.CharField(read_only=True, source="document.title")
    file = serializers.FileField(read_only=True, use_url=False, source="document.file")
    size = serializers.IntegerField(read_only=True, source="document.file.size")
    ordering = serializers.IntegerField(read_only=True)


class ProductDetailOutputSerializer(ProductListOutputSerializer, SEOMixin):
    image = serializers.SerializerMethodField(read_only=True)
    # documents = NestedDocumentSerializer(read_only=True, many=True, source="product_documents")
    documents = serializers.SerializerMethodField(read_only=True)
    category = serializers.SerializerMethodField(read_only=True)
    description = serializers.CharField()
    breadcrumbs = serializers.SerializerMethodField(read_only=True)
    properties = ProductPropertySerializer(read_only=True, many=True, source="properties_through")  # type: ignore
    same_category_products = serializers.SerializerMethodField(read_only=True)
    related_products = serializers.SerializerMethodField(read_only=True)

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

    def get_same_category_products(self, obj):
        products = get_same_category_products(obj)
        return ProductListOutputSerializer(
            products,
            many=True,
            context={"request": self.context["request"]},
        ).data

    def get_related_products(self, obj):
        products = get_related_products(obj)
        return ProductListOutputSerializer(
            products,
            many=True,
            context={"request": self.context["request"]},
        ).data

    def get_image(self, obj):
        img_path = get_img_path(obj)
        return img_path

    def get_documents(self, obj: Product):
        product_documents = obj.product_documents.filter(document__is_published=True)
        primary_category = obj.categories.filter(product_categories__is_primary=True).first()
        if not primary_category:
            return NestedDocumentSerializer(product_documents, many=True).data
        category_documents = primary_category.category_documents.filter(document__is_published=True)
        doc_qs = category_documents.union(product_documents).order_by("ordering")
        return NestedDocumentSerializer(doc_qs, many=True).data


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
    documents = NestedDocumentSerializer(read_only=True, many=True, source="category_documents")
    min_price = serializers.SerializerMethodField()
    max_price = serializers.SerializerMethodField()
    products_count = serializers.SerializerMethodField()

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

    def get_min_price(self, obj):
        min_ton_price = obj.products.aggregate(min_ton_price=Min("ton_price"))["min_ton_price"]
        min_unit_price = obj.products.aggregate(min_unit_price=Min("unit_price"))["min_unit_price"]
        min_meter_price = obj.products.aggregate(min_meter_price=Min("meter_price"))["min_meter_price"]
        min_price = min_ton_price or min_meter_price or min_unit_price
        return float(min_price * obj.price_coefficient) if min_price else 0

    def get_max_price(self, obj):
        max_ton_price = obj.products.aggregate(max_price=Max("ton_price"))["max_price"]
        max_unit_price = obj.products.aggregate(max_price=Max("unit_price"))["max_price"]
        max_meter_price = obj.products.aggregate(max_price=Max("meter_price"))["max_price"]
        max_price = max_ton_price or max_meter_price or max_unit_price
        return float(max_price * obj.price_coefficient) if max_price else 0

    def get_products_count(self, obj):
        return obj.products.count()

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


class SitemapSerializer(serializers.Serializer):
    loc = serializers.SerializerMethodField(read_only=True)
    lastmod = serializers.DateTimeField(read_only=True, source="updated_date", format="%Y-%m-%d")

    def get_loc(self, obj):
        front_slug = self.context.get("front_slug", "catalog")
        return f'https://{settings.DOMAIN}/{front_slug}/{obj.get("slug")}'


class CatalogNewLeftMenuSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(source="data.name")
    slug = serializers.CharField(source="data.slug")
    image = serializers.CharField(source="data.image")
    is_published = serializers.BooleanField(source="data.is_published")
    children = serializers.SerializerMethodField(default=[])

    def get_children(self, obj):
        res = []
        children = obj.get("children", [])
        for child in children:
            res.append(CatalogNewLeftMenuSerializer(child).data)
        return res


# class ProductInOrderCreateSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = ProductInOrder
#         fields = ["order", "product", "quantity"]


# class ProductInOrderOutputSerializer(serializers.ModelSerializer):
#     product = ProductListOutputSerializer(read_only=True)

#     class Meta:
#         model = ProductInOrder
#         fields = ["order", "product", "quantity"]
#         extra_kwargs = {"order": {"write_only": True}}


class CreateFormSubmissionSerializer(serializers.ModelSerializer):
    # products = ProductInOrderOutputSerializer(many=True, read_only=True, source="product_in_orders")

    class Meta:
        model = FormSubmission
        fields = [
            "title",
            "url",
            # "product",
            "phone",
            "name",
            "email",
            "question",
            "created_date",
            "updated_date",
        ]


class DocumentListSerializer(serializers.ModelSerializer):
    size = serializers.IntegerField(read_only=True, source="file.size")
    categories = CategoryListOutputSerializer(many=True, read_only=True)  # type: ignore

    class Meta:
        model = Document
        fields = [
            "title",
            "file",
            "size",
            "categories",
            "ordering",
        ]
        extra_kwargs = {
            "file": {"use_url": False},
        }

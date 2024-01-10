from decimal import ROUND_CEILING

from django.contrib import admin
from django.utils.html import format_html
from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from backend.catalog.models import (
    Category,
    Product,
    ProductCategories,
    ProductProperty,
    ProductPropertyValue,
)


class PropertyInline(admin.TabularInline):
    model = ProductProperty.categories.through
    raw_id_fields = ["productproperty"]
    verbose_name = "Свойство продукта"
    verbose_name_plural = "Свойства продуктов"


@admin.register(Category)
class CategoryAdmin(TreeAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = (
        "cat_name",
        "slug",
        "is_published",
        "is_parsing_successful",
        "id",
    )
    list_editable = ("is_published",)
    list_filter = ["is_published"]
    inlines = [PropertyInline]
    search_fields = ["parsed_name", "name"]
    readonly_fields = ["updated_date", "created_date", "parse_url"]
    form = movenodeform_factory(Category)
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "name",
                    "image",
                    "product_image",
                    "description",
                    "weight_coefficient",
                    "price_coefficient",
                    "is_published",
                    "_position",
                    "_ref_node_id",
                ],
            },
        ),
        (
            "Парсинг",
            {
                "classes": ("collapse", "wide"),
                "fields": [
                    "parsed_name",
                    "parse_url",
                    "last_parsed_at",
                    "is_parsing_successful",
                ],
            },
        ),
        (
            "SEO",
            {
                "classes": ("collapse", "wide"),
                "fields": [
                    "slug",
                    "seo_title",
                    "seo_description",
                    "h1",
                    "is_index",
                    "is_follow",
                    "ordering",
                ],
            },
        ),
    ]

    @admin.display(description="Название категории")
    def cat_name(self, obj):
        return obj.name if obj.name else obj.parsed_name


class ProductPropertyInline(admin.TabularInline):
    model = ProductPropertyValue
    extra = 2
    fk_name = "product"
    raw_id_fields = ("property",)


class ProductCategoriesInline(admin.TabularInline):
    model = ProductCategories
    extra = 2
    fk_name = "product"
    raw_id_fields = ("category",)


class LeafPublishedCategories(admin.SimpleListFilter):
    """Фильтр для сортировки по главной категории, только если она является
    листом и опубликована"""

    title = "По главной категории"
    parameter_name = "category"

    def lookups(self, request, model_admin):
        return list(
            Category.objects.filter(is_published=True, depth=3)
            .values_list("slug", "name")
            .order_by("path")
        )

    def queryset(self, request, qs):
        value = self.value()
        if value:
            return qs.filter(categories__slug=value)
        return qs


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = (
        "name",
        # "category",
        "slug",
        "custom_ton_price",
        "custom_unit_price",
        "custom_meter_price",
        "parsed_price",
        "cat_price_coefficient",
        "id",
        "in_stock",
        "always_in_stock",
        "is_published",
        # "prop_values_list",
    )
    # exclude = ["prop_values"]
    list_editable = (
        "is_published",
        "custom_ton_price",
        "custom_unit_price",
        "custom_meter_price",
        "always_in_stock",
    )
    list_filter = [LeafPublishedCategories, "in_stock", "always_in_stock"]
    search_fields = ["name", "id"]
    inlines = [ProductPropertyInline, ProductCategoriesInline]
    readonly_fields = [
        "updated_date",
        "created_date",
        "in_stock",
        "ton_price",
        "unit_price",
        "meter_price",
    ]
    # inlines = [ProductCategoriesInline, PropertyValueInline]

    @admin.display(description="Коэфициент")
    def cat_price_coefficient(self, obj):
        main_category = obj.categories.filter(
            product_categories__is_primary=True
        ).first()
        if main_category:
            return main_category.price_coefficient
        else:
            return "-"

    @admin.display(description="Автоцены")
    def parsed_price(self, obj):
        return format_html(
            f"тн: {str(int(obj.ton_price.quantize(1, rounding=ROUND_CEILING)))}<br>"
            f"м: {str(int(obj.meter_price.quantize(1, rounding=ROUND_CEILING)))}<br>"
            f"шт: {str(int(obj.unit_price.quantize(1, rounding=ROUND_CEILING)))}"
        )

    # def prop_values_list(self, obj):
    #     return ", ".join([p.value for p in obj.prop_values.all()])

    # prop_values_list.short_description = "Значения свойств"


class PropertyValuesCategoryFilter(admin.SimpleListFilter):
    """Фильтр для сортировки по главной категории, только если она является
    листом и опубликована"""

    title = "По главной категории"
    parameter_name = "product__categories"

    def lookups(self, request, model_admin):
        return list(
            Category.objects.filter(is_published=True, depth=3)
            .values_list("slug", "name")
            .order_by("path")
        )

    def queryset(self, request, qs):
        value = self.value()
        if value:
            return qs.filter(product__categories__slug=value)
        return qs


@admin.register(ProductPropertyValue)
class ProductPropertyValueAdmin(admin.ModelAdmin):
    list_display = ("product", "property", "value")
    list_filter = ("property", PropertyValuesCategoryFilter)
    list_editable = ("value",)


@admin.register(ProductProperty)
class ProductPropertyAdmin(admin.ModelAdmin):
    prepopulated_fields = {"code": ("name",)}
    list_display = (
        "name",
        "code",
        "units",
        "ordering",
        "id",
        "is_display_in_list",
        "is_published",
        "is_sortable",
    )
    list_editable = (
        "is_published",
        "units",
        "ordering",
        "is_display_in_list",
        "is_sortable",
    )
    list_filter = ["categories"]

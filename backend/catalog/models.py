from functools import partial

from django.db import models
from django_extensions.db.models import AutoSlugField
from slugify import slugify
from treebeard.mp_tree import MP_Node


class BaseModel(models.Model):
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(verbose_name="Опубликовано", default=False)
    ordering = models.PositiveSmallIntegerField(verbose_name="Порядок", default=500)

    class Meta:
        abstract = True
        ordering = ("ordering",)


class SEOModel(models.Model):
    slug = AutoSlugField(
        verbose_name="slug",
        editable=True,
        blank=False,
        populate_from="name",
        slugify_function=partial(slugify, replacements=[["я", "ya"], ["/", ""]]),
        max_length=150,
    )
    seo_title = models.CharField(max_length=350, blank=True, verbose_name="SEO Title")
    seo_description = models.CharField(
        max_length=500, blank=True, verbose_name="SEO Description"
    )
    h1 = models.CharField(max_length=250, blank=True, verbose_name="H1")
    is_index = models.BooleanField(verbose_name="Robots index", default=True)
    is_follow = models.BooleanField(verbose_name="Robots follow", default=True)

    class Meta:
        abstract = True


class Category(BaseModel, SEOModel, MP_Node):  # type: ignore
    parsed_name = models.CharField(
        verbose_name="Название категории из парсинга", max_length=500, blank=True
    )
    name = models.CharField(verbose_name="Название категории", max_length=500)
    description = models.TextField(verbose_name="Описание", max_length=1500, blank=True)
    parse_url = models.URLField(verbose_name="URL парсинга", blank=True, max_length=500)
    weight_coefficient = models.DecimalField(
        verbose_name="Коэфициент веса", max_digits=20, decimal_places=2, default=1.00
    )
    price_coefficient = models.DecimalField(
        verbose_name="Коэфициент цены", max_digits=20, decimal_places=2, default=1.00
    )
    last_parsed_at = models.DateTimeField(
        verbose_name="Дата последнего парсинга", blank=True, null=True
    )
    is_parsing_successful = models.BooleanField(
        verbose_name="Парсинг успешный", default=False
    )
    image = models.ImageField(
        verbose_name="Изображение", upload_to="categories/", blank=True
    )

    node_order_by = ["name"]

    def __str__(self) -> str:
        return self.name if self.name else self.parsed_name

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        db_table = "catalog_category"


class ProductProperty(BaseModel):
    name = models.CharField(verbose_name="Название свойства", max_length=250)
    code = AutoSlugField(
        verbose_name="Код свойства",
        editable=True,
        blank=False,
        populate_from="name",
        slugify_function=slugify,
    )
    description = models.CharField(verbose_name="Описание", max_length=2500, blank=True)
    categories = models.ManyToManyField(
        Category, verbose_name="Категории продуктов", related_name="product_properties"
    )
    units = models.CharField(
        verbose_name="Единицы измерения", max_length=250, blank=True
    )
    is_display_in_list = models.BooleanField(
        verbose_name="Отображать в списке продкутов?", default=False
    )

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = "Свойство товара"
        verbose_name_plural = "Свойства товаров"
        ordering = ("ordering",)
        db_table = "catalog_product_property"


class Product(BaseModel, SEOModel):
    # images
    name = models.CharField(verbose_name="Название продукта", max_length=500)
    description = models.TextField(verbose_name="Описание", max_length=2500, blank=True)
    parse_url = models.URLField(verbose_name="URL парсинга", blank=True, max_length=500)
    unit_price = models.DecimalField(
        verbose_name="Цена за штуку",
        max_digits=20,
        decimal_places=2,
        default=0.00,
        help_text="Рассчитывается автоматически, если указан вес метра и длина",
    )
    ton_price = models.DecimalField(
        verbose_name="Цена за тонну",
        max_digits=20,
        decimal_places=2,
        default=0.00,
        help_text="Спаршеная цена за тонну, обновляется сама",
    )
    meter_price = models.DecimalField(
        verbose_name="Цена за метр",
        max_digits=20,
        decimal_places=2,
        default=0.00,
        help_text="Рассчитывается автоматически, если указан вес метра",
    )
    custom_ton_price = models.DecimalField(
        verbose_name="Своя цена за тонну",
        max_digits=20,
        decimal_places=2,
        default=0.00,
        help_text="Приоритет отображения цены выше, чем у спаршеной",
    )
    custom_unit_price = models.DecimalField(
        verbose_name="Своя цена за штуку",
        max_digits=20,
        decimal_places=2,
        default=0.00,
        help_text="Приоритет отображения цены выше, чем у спаршеной",
    )
    custom_meter_price = models.DecimalField(
        verbose_name="Своя цена за метр",
        max_digits=20,
        decimal_places=2,
        default=0.00,
        help_text="Приоритет отображения цены выше, чем у спаршеной",
    )
    categories = models.ManyToManyField(
        Category,
        verbose_name="Категории",
        related_name="products",
        through="ProductCategories",
    )
    properties = models.ManyToManyField(
        ProductProperty,
        verbose_name="Свойства",
        related_name="products",
        through="ProductPropertyValue",
    )
    in_stock = models.BooleanField(verbose_name="В наличии", default=True)
    always_in_stock = models.BooleanField(
        verbose_name="Всегда в наличии",
        default=False,
        help_text="Не зависит от парсинга, имеет высший приоритет",
    )

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        db_table = "catalog_product"


class ProductCategories(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="product_categories"
    )
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="product_categories"
    )
    is_primary = models.BooleanField(verbose_name="Главная категория", default=False)
    is_display = models.BooleanField(
        verbose_name="Отображать в категории?", default=False
    )

    class Meta:
        db_table = "catalog_product_categories"


class ProductPropertyValue(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="properties_through"
    )
    property = models.ForeignKey(
        ProductProperty, on_delete=models.CASCADE, related_name="values_through"
    )
    value = models.CharField(verbose_name="Значение", max_length=250, blank=True)

    class Meta:
        unique_together = ("product", "property")
        verbose_name = "Значение свойства продукта"
        verbose_name_plural = "Значения свойств продукта"
        ordering = ("property__ordering",)
        db_table = "catalog_product_property_value"

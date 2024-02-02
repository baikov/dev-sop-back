from django.db.models.query import QuerySet

from backend.catalog.models import Product


def add_product_properties(product: Product) -> None:
    """
    Создает записи таблицы ProductPropertyValue (Свойство - Значение) для вновь
    созданного Продукта на основе принадлежности к Категории
    """
    category = product.categories.filter(product_categories__is_primary=True).first()
    if category is None:
        return
    properties = category.product_properties.difference(product.properties.all())
    for property in properties:
        product.properties_through.create(property=property)


def remove_redundant_product_properties(product: Product) -> None:
    """
    Удаляет записи таблицы ProductPropertyValue (Свойство - Значение) для Продукта
    при смене Категории
    """
    # TODO: проверить на корректность работы
    pass
    # category = product.categories.filter(product_categories__is_primary=True).first()
    # remove_properties = product.properties.difference(
    # category.product_properties.all()
    # )
    # product.properties_through.filter(
    #     property_id__in=Subquery(remove_properties.values("id"))
    # ).delete()
    # # product.properties_through.filter(property__in=remove_properties).delete()


def get_same_category_products(product: Product) -> QuerySet:
    category = product.categories.filter(product_categories__is_primary=True).first()
    if category is None:
        return Product.objects.none()
    else:
        products = category.products.filter(is_published=True).exclude(id=product.id)[
            :5
        ]

    return products


def get_related_products(product: Product) -> QuerySet:
    products = Product.objects.filter(
        is_published=True,
    )
    return products[:5]


def get_img_path(product: Product) -> str | None:
    main_cateory = product.categories.filter(
        product_categories__is_primary=True
    ).first()
    if product.image:
        img_url = product.image.name
    elif main_cateory is not None and main_cateory.product_image:
        img_url = main_cateory.product_image.name
    elif main_cateory is not None and main_cateory.image:
        img_url = main_cateory.image.name
    else:
        img_url = None
    return img_url

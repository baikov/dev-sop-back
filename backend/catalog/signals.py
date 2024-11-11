import math
import os

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from slugify import slugify

from backend.catalog.models import (
    Category,
    CategoryProductProperties,
    Document,
    Product,
    ProductPropertyValue,
)
from backend.catalog.services.categories import add_category_products_properties, remove_category_product_properties

# @receiver(m2m_changed, sender=ProductProperty.categories.through)
# def property_added_to_category(sender, instance, action, reverse, **kwargs):
#     """
#     Обработчик изменения категорий продукта
#     """
#     logger.info(f"Action: {action}")
#     logger.info(f"Reverse: {reverse}")
#     logger.warning(f"Instance {instance}")

#     if action == "post_add":
#         logger.info("post_add")


@receiver(post_save, sender=CategoryProductProperties)
def property_added_to_category(sender, instance, **kwargs):
    """
    При добавлении свойства к категории - добавить это свойство для всех продуктов категории с пустыми значениями
    """
    add_category_products_properties(instance)


@receiver(post_delete, sender=CategoryProductProperties)
def property_removed_from_category(sender, instance, **kwargs):
    """
    При удалении свойства из категории - удалить это свойство для всех продуктов категории
    """
    remove_category_product_properties(instance)


@receiver(pre_save, sender=Product)
def generate_slug_signal(sender, instance, **kwargs):
    if instance.slug == "":
        instance.slug = slugify(instance.name)


@receiver(pre_save, sender=Category)
def fill_category_name_signal(sender, instance, **kwargs):
    if instance.name == "":
        instance.name = instance.parsed_name


# @receiver(post_save, sender=Category)
# def fill_child_categories_properties_signal(sender, instance, **kwargs):
#     if not instance.is_leaf() and instance.product_properties.exists():
#         for child in instance.get_children():
#             child.product_properties.clear()
#             child.product_properties.add(*instance.product_properties.all())


@receiver(post_save, sender=Product)
def manage_product_properties_signal(sender, instance, **kwargs):
    """
    Если указана главная категория - добавить нужные свойства к товару, удалить ненужные
    """
    # add_product_properties(instance)
    # remove_redundant_product_properties(instance)
    pass


# @receiver([post_save, post_delete], sender=PropCat, dispatch_uid="cat_prop_changed")
# def cat_prop_changed(sender, instance, **kwargs):
#     logger.debug("PropCat post_save")


@receiver(post_save, sender=ProductPropertyValue)
def calculate_prices_when_update_property_signal(sender, instance, **kwargs):
    """
    Если указана длина и вес тонны - рассчитываем вес штуки, цену метра и цену штуки
    """
    meter_price = instance.product.meter_price
    meter_weight = None
    ton_price = instance.product.custom_ton_price if instance.product.custom_ton_price else instance.product.ton_price
    if instance.property.code == "ves-metra" and ton_price:
        try:
            meter_weight = float(instance.value.replace(",", "."))
        except ValueError:
            pass
        if meter_weight:
            meter_price = math.ceil(float(ton_price) / 1_000 * meter_weight)
            instance.product.meter_price = meter_price
            instance.product.save()

    if instance.property.code == "dlina" and meter_price:
        try:
            length = int(instance.value.split("-")[0]) if "-" in instance.value else int(instance.value)
        except ValueError:
            pass

        if length:
            instance.product.unit_price = math.ceil(float(meter_price) * length / 1000)
            instance.product.save()


@receiver(pre_save, sender=Product)
def calculate_prices_when_ton_price_updated_signal(sender, instance, **kwargs):
    length = meter_weight = None
    ton_price = float(instance.custom_ton_price) or float(instance.ton_price)
    meter_weight_instance = ProductPropertyValue.objects.filter(
        product=instance,
        property__code="ves-metra",
    ).first()
    if meter_weight_instance:
        try:
            meter_weight = float(meter_weight_instance.value.replace(",", "."))
        except ValueError:
            pass
    length_instance = ProductPropertyValue.objects.filter(
        product=instance,
        property__code="dlina",
    ).first()

    if length_instance:
        try:
            length = (
                int(length_instance.value.split("-")[0]) if "-" in length_instance.value else int(length_instance.value)
            )
        except ValueError:
            pass

    if ton_price and meter_weight:
        instance.meter_price = math.ceil(ton_price / 1_000 * meter_weight)
        if length:
            instance.unit_price = math.ceil(instance.meter_price * length / 1000)


@receiver(pre_save, sender=Document)
def slugify_file_name_signal(sender, instance: Document, **kwargs):
    if instance.file and not instance.title:
        original_name, ext = os.path.splitext(instance.file.name)
        parts = original_name.split("/")
        parts[-1] = slugify(parts[-1])
        instance.title = "/".join(parts) + ext

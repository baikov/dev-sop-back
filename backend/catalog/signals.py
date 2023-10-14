import math

from django.db.models.signals import post_save, pre_save  # m2m_changed, post_delete,
from django.dispatch import receiver
from slugify import slugify

from backend.catalog.models import (  # ProductProperty,
    Category,
    Product,
    ProductPropertyValue,
)

# from backend.products.services.products import add_product_properties


@receiver(pre_save, sender=Product)
def generate_slug_signal(sender, instance, **kwargs):
    if instance.slug == "":
        instance.slug = slugify(instance.name)


@receiver(pre_save, sender=Category)
def fill_category_name_signal(sender, instance, **kwargs):
    if instance.name == "":
        instance.name = instance.parsed_name


@receiver(post_save, sender=Category)
def fill_child_categories_properties_signal(sender, instance, **kwargs):
    if not instance.is_leaf() and instance.product_properties.exists():
        for child in instance.get_children():
            child.product_properties.clear()
            child.product_properties.add(*instance.product_properties.all())


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
    ton_price = (
        instance.product.custom_ton_price
        if instance.product.custom_ton_price
        else instance.product.ton_price
    )
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
            length = (
                int(instance.value.split("-")[0])
                if "-" in instance.value
                else int(instance.value)
            )
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
                int(length_instance.value.split("-")[0])
                if "-" in length_instance.value
                else int(length_instance.value)
            )
        except ValueError:
            pass

    if ton_price and meter_weight:
        instance.meter_price = math.ceil(ton_price / 1_000 * meter_weight)
        if length:
            instance.unit_price = math.ceil(instance.meter_price * length / 1000)

import re
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
from celery import current_task, shared_task  # group
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from loguru import logger
from requests.exceptions import HTTPError, RequestException
from treebeard.mp_tree import MP_Node

from backend.catalog.models import (
    Category,
    Product,
    ProductProperty,
    ProductPropertyValue,
)
from backend.utils.custom import get_object_or_None

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
    "Connection": "keep-alive",  # close
    "Cache-Control": "no-cache",  # max-age 3600
    "Accept-Language": "ru-RU",
    "Accept-Encoding": "gzip, deflate, br",
}


@dataclass
class ParsedProduct:
    in_stock: bool
    name: str
    parse_url: str
    size: str
    mark: str
    length: str
    idt: str
    idf: str
    idb: str
    price: float
    weight: str = ""


@shared_task
def parse_categories_task() -> list[dict[str, object]]:
    """
    This function parses categories from a sitemap and saves them to a database.
    :return: A list of dictionaries representing the parsed categories.
    :rtype: List[Dict[str, object]]
    """
    host: str = "https://mc.ru"
    path: str = "/sitemap/map"
    cat_for_parse: list[str] = [
        "Сортовой прокат",
        "Трубы",
        "Листовой прокат",
    ]
    categories: list[dict[str, object]] = []

    try:
        response = requests.get(host + path, headers=HEADERS)
        response.raise_for_status()

    except requests.exceptions.RequestException as e:
        logger.error("Error: {}", e)
        return categories

    soup = BeautifulSoup(response.text, "html.parser")
    main_categories = soup.find_all("section", class_="category")

    for cat in main_categories:
        if cat.h2 is None or cat.h2.a is None:
            continue
        name: str = cat.h2.a.text
        if name not in cat_for_parse:
            continue
        href: str = host + cat.h2.a["href"]
        slug: str = href.split("/")[-1].replace("_", "-")
        category: dict[str, Any] = {
            "name": name,
            "href": href,
            "slug": slug,
            "children": [],
        }

        level2 = cat.find("div", class_="sections")
        subcats = level2.find_all("section", class_="group")
        for subcat in subcats:
            if subcat.h3 is None or subcat.h3.a is None:
                continue
            name = subcat.h3.a.text
            href = host + subcat.h3.a["href"]
            slug = href.split("/")[-1].replace("_", "-")
            subcategory: dict[str, Any] = {
                "name": name,
                "href": href,
                "slug": slug,
                "children": [],
            }

            lv3 = subcat.find_all("li")
            for item in lv3:
                if item.a is None:
                    continue
                name = item.a.text
                href = host + item.a["href"]
                slug = href.split("/")[-1].replace("_", "-")
                subsubcat = {
                    "name": name,
                    "href": href,
                    "slug": slug,
                }
                subcategory["children"].append(subsubcat)

            category["children"].append(subcategory)
        categories.append(category)

    # Save categories to database
    with transaction.atomic():
        for cat in categories:
            category_instance: MP_Node = Category.add_root(
                parsed_name=cat["name"], parse_url=cat["href"]
            )

            for subcat in cat["children"]:
                subcategory_instance: MP_Node = category_instance.add_child(
                    parsed_name=subcat["name"], parse_url=subcat["href"]
                )

                for subsubcat in subcat["children"]:
                    subcategory_instance.add_child(
                        parsed_name=subsubcat["name"], parse_url=subsubcat["href"]
                    )

    return categories


@shared_task(soft_time_limit=600)
def parse_products_task(categories_ids: list[int]):
    # categories_id = Category.objects.values_list("id", flat=True)
    # tasks = [
    #     parse_category_products_task.s(category_id) for category_id in categories_id
    # ]

    # task_group = group(tasks)
    # result = task_group.apply_async()
    # result.ready()
    # # дальнейшая логика
    # if result.successful():
    #     logger.info("Все задачи выполнены успешно")
    # else:
    #     logger.error("Парсинг завершился с ошибкой: {}", result.failed())

    categories_id = [
        cat.id
        for cat in Category.objects.filter(
            Q(id__in=categories_ids)
            & (
                Q(is_parsing_successful=False)
                | Q(last_parsed_at__lt=timezone.now() - timedelta(days=1))
                | Q(last_parsed_at__isnull=True)
            )
        )
        if cat.is_leaf()
    ]

    for category_id in categories_id:
        parse_category_products_task.delay(category_id)
        time.sleep(15)


def _is_in_stock(product: Tag) -> bool:
    button_tag = product.find("button")
    class_value = button_tag.get("class") if button_tag else None
    logger.debug("Класс кнопки: {}", class_value)
    # class_list = class_value.split() if class_value else None
    if not class_value:
        logger.error("Не удалось определить наличие у товара: {}", product["data-nm"])
        return False

    return True if "_basket" in class_value else False


def _get_product_price(product: Tag) -> float:
    try:
        price = float(product.find("meta", itemprop="price")["content"].strip())
    except ValueError:
        logger.info(
            "Цена отсутствует: {}",
        )
        price = 0.0
    return price


def _get_product_weight(idt: str, idf: str, idb: str) -> str | None:
    if idt and idf and idb:
        weight_url = (
            "https://mc.ru/pages/blocks/add_basket.asp/id/"
            + f"{idt}/idf/{idf}/idb/{idb}"
        )
        logger.debug("weight_url: {}", weight_url)

        try:
            response = requests.get(weight_url, headers=HEADERS)
            response.raise_for_status()

        except RequestException as e:
            logger.error("Error: {}", e)

        soup = BeautifulSoup(response.text, "html.parser")
        script = soup.find("script", language="Javascript")
        # Получаем значение переменной
        k = re.search("var k=(.*?);", script.text)
        if k is None:
            logger.error("Не удалось получить значение переменной")
            return "Regexp failed"
        found = k.group(1)
        weight = float(found) * 1000
        logger.debug("weight: {}", weight)

        return str(weight)
    return None


def get_unique_products(soup: BeautifulSoup) -> dict[str, ParsedProduct]:
    parsed_products: dict[str, ParsedProduct] = {}
    host = "https://mc.ru"

    # Логика
    for product in soup.find_all("tr", itemtype="http://schema.org/Product"):
        # определяем, в наличии ли товар (трубка или корзинка)
        in_stock = _is_in_stock(product)
        name = re.sub(r"\s+", " ", product["data-nm"])
        name = re.sub(r"(?<=\d)х(?=\d)", "x", name)
        parse_url = host + product.find("a")["href"]
        size = product.find("td", class_="_razmer").text.strip()
        mark = product.find("td", class_="_mark").text.strip()
        length = product.find("td", class_="_dlina").text.strip()
        logger.info("Длина товара: {}", length)

        # получаем цену товара
        price = _get_product_price(product)

        parsed_product = ParsedProduct(
            name=name.capitalize(),
            price=price,
            in_stock=in_stock,
            parse_url=parse_url,
            length=length,
            mark=mark,
            size=size,
            idt=product["idt"],
            idf=product["idf"],
            idb=product["idb"],
        )

        # existing_product = parsed_products.get(parse_url)
        # оставляем только уникальные названия
        existing_product = parsed_products.get(name)
        logger.debug("ex: {}\npars: {}", existing_product, parsed_product)
        # TODO: проверить не нулевая ли цена
        if existing_product is None:
            parsed_products[name] = parsed_product
        elif parsed_product.price < existing_product.price and parsed_product.in_stock:
            parsed_products[name] = parsed_product
        elif not existing_product.in_stock and parsed_product.in_stock:
            parsed_products[name] = parsed_product

    return parsed_products


# def parse_category_properties(soup: BeautifulSoup):
#     filter_body = soup.find("div", class_="filtr-body")
#     filters_html = filter_body.select("div.sidebarBlock.filtr")

#     for filter in filters_html:
#         prop_name = filter.find("h4").text.strip()
#         property_instance, property_is_created = (
#           ProductProperty.objects.get_or_create(
#             name=prop_name
#         ))
#         if property_is_created:
#             logger.debug("Добавлено свойство: {}", property_instance)

#         for value_items in filter.find_all("li"):
#             value_instance, value_is_created = PropertyValue.objects.get_or_create(
#                 property=property_instance,
#                 value=value_items.div.a.text.strip(),
#             )
#             if value_is_created:
#                 logger.debug("Добавлено значение: {}", value_instance)


@shared_task(
    autoretry_for=(HTTPError,),
    max_retries=3,
    # retry_backoff=True,  # экспоненциальная задержка
    # retry_backoff_max=700,  #  максимальное смещение по времени
    retry_jitter=True,  # случайное смещение по времени при повторе
    retry_delay=60 * 5,
)
def parse_category_products_task(category_id: int):
    # https://mc.ru/metalloprokat/listovoy
    # https://mc.ru/region/nnovgorod/metalloprokat/listovoy/PageAll/1

    # Достаем все продукты категории и категорию в один запрос
    category = Category.objects.prefetch_related(
        Prefetch(
            "products",
            queryset=Product.objects.filter(product_categories__is_primary=True),
            to_attr="category_products",
        )
    ).get(id=category_id)

    category_products: list = category.category_products

    # category = Category.objects.get(id=category_id)
    # products = category.products.filter(product_categories__is_primary=True)

    url: str = (
        category.parse_url.replace("https://mc.ru", "https://mc.ru/region/nnovgorod")
        + "/PageAll/1"
    )
    category.last_parsed_at = timezone.now()

    try:
        response = requests.get(url, headers=HEADERS)  # allow_redirects=False
        # if response.status_code == 302:
        #     raise Exception("Блок парсинга")
        response.raise_for_status()

    except requests.exceptions.RequestException as e:
        logger.error(
            "Ошибка при отправке запроса на получение категории {}: {}",
            category.parsed_name,
            e,
        )
        category.is_parsing_successful = False
        category.save()
        current_task().raise_exception(e)

    soup = BeautifulSoup(response.text, "html.parser")

    # Проверяем, не выкинули нам капчу
    is_check_human = soup.find("form", action="/check-human")
    if is_check_human:
        category.is_parsing_successful = False
        category.save()
        raise HTTPError("Блокировка парсинга", response=response)

    category_is_empty = soup.find("div", class_="catalogItems _empty")
    if category_is_empty:
        category.is_parsing_successful = True
        category.save()
        return f"Категория {category.parsed_name} пуста"

    category_title = re.sub(
        r"\s+",
        " ",
        soup.find("title").text.strip().replace("МЕТАЛЛСЕРВИС", "СПЕЦОПТТОРГ"),
    )[:350]
    category_description = re.sub(
        r"\s+",
        " ",
        soup.find("meta", attrs={"name": "description"})["content"]
        .strip()
        .replace("МЕТАЛЛСЕРВИС", "СПЕЦОПТТОРГ")
        .replace("стране", "городе"),
    )[:500]
    category_h1 = re.sub(
        r"\s+",
        " ",
        soup.find("h1").text.strip().replace("МЕТАЛЛСЕРВИС", ""),
    )[:250]

    if not category.seo_title:
        category.seo_title = category_title
    if not category.seo_description:
        category.seo_description = category_description
    if not category.h1:
        category.h1 = category_h1

    category.save()

    # Если категория не лист дерева категорий, то выход
    if not category.is_leaf():
        return

    parsed_products = get_unique_products(soup)
    logger.debug("Получено {} продуктов", len(parsed_products))

    # Логика обновления продкутов в БД
    instances_update_count = 0
    instances_create_count = 0
    exist_in_parsed_products = []
    for name, product in parsed_products.items():
        # product_instance = get_object_or_None(Product, parse_url=parse_url)
        try:
            product_instance = next(
                p for p in category_products if p.parse_url == product.parse_url
            )
        except StopIteration:
            # продукт с таким именем не найден
            product_instance = None

        # продукт существует в БД - обновляем
        if product_instance:
            product_instance.in_stock = product.in_stock
            product_instance.ton_price = product.price
            exist_in_parsed_products.append(product_instance.id)
            # счетчик обновлений
            instances_update_count += 1
        else:
            product_instance = Product(
                name=product.name,
                parse_url=product.parse_url,
                ton_price=product.price,
                in_stock=product.in_stock,
                is_published=True,  # if product.in_stock else False,
            )
            # счетчик созданий
            instances_create_count += 1
            # Тут можно парсить вес и картинку с детальной страницы
            # weight = _get_product_weight(product.idt, product.idf, product.idb)
            # ProductPropertyValue.objects.get_or_create(
            #     product=product_instance,
            #     property=ProductProperty.objects.get(code="ves-metra"),
            #     value=weight,
            # )

        product_instance.save()
        product_instance.categories.add(
            category,
            through_defaults={"is_display": True, "is_primary": True},
        )

        # size, mark, length
        size_is_h = [
            "Балки (Двутавр)",
            "Балки (Двутавр) низколегированные",
            "Швеллер",
            "Швеллер гнутый",
            "Швеллер низколегированный",
            "Уголок неравнополочный",
            "Уголок нержавеющий никельсодержащий",
            "Уголок равнополочный",
            "Уголок равнополочный низколегированный",
            "Уголок равнополочный судостроительный",
            "Лист г/к",
            "Лист г/к конструкционный",
            "Лист г/к мостостроительный",
            "Лист г/к низколегированный",
            "Лист г/к Ст3",
            "Лист г/к судостроительный",
            "Лист нержавеющий без никеля",
            "Лист нержавеющий никельсодержащий",
            "Лист нержавеющий ПВЛ",
            "Лист оцинкованный",
            "Лист рифленый",
            "Лист холоднокатанный х/к",
            "Лист холоднокатанный х/к Ст",
            "Лист просечно-вытяжной (ПВЛ)",
        ]
        size_is_b = [
            "Полоса оцинкованная",
            "Квадрат  горячекатаный",
            "Полоса г/к",
            "Полоса г/к оцинкованная",
            "Полоса нержавеющая никельсодержащая",
        ]
        length_is_poverkhnost = [
            "Лист г/к",
            "Лист г/к конструкционный",
            "Лист г/к мостостроительный",
            "Лист г/к низколегированный",
            "Лист г/к Ст3",
            "Лист г/к судостроительный",
            "Лист нержавеющий без никеля",
            "Лист нержавеющий никельсодержащий",
            "Лист нержавеющий ПВЛ",
            "Лист оцинкованный",
            "Лист рифленый",
            "Лист холоднокатанный х/к",
            "Лист холоднокатанный х/к Ст",
            "Лист просечно-вытяжной (ПВЛ)",
        ]
        mark_is_dlina = [
            "Лист рифленый",
        ]
        mark_is_shirina = [
            "Рулоны г/к",
            "Рулоны нержавеющие",
            "Рулоны оцинкованные",
            "Рулоны оцинкованные с полимерным покрытием",
            "Рулоны х/к",
        ]
        mark_is_stenka = [
            "Трубы стальные горячедеформированные",
            "Трубы стальные холоднодеформированные",
        ]
        mark_is_none = [
            "Трубы оцинкованные квадратные",
            "Трубы оцинкованные круглые",
            "Трубы оцинкованные прямоугольные",
            "Доборные элементы",
            "Саморезы кровельные",
        ]
        mark_is_profil = [
            "Профнастил Н114",
            "Профнастил Н57",
            "Профнастил Н60",
            "Профнастил Н75",
            "Профнастил НС35",
            "Профнастил НС44",
            "Профнастил окрашенный",
            "Профнастил оцинкованный",
            "Профнастил С10",
            "Профнастил С20",
            "Профнастил С21",
            "Профнастил С44",
            "Профнастил С8",
        ]

        if category.parsed_name in size_is_h:
            size_code = "vysota-h"
        elif category.parsed_name in size_is_b:
            size_code = "shirina-b"
        else:
            size_code = "diametr"

        if category.parsed_name in mark_is_dlina:
            mark_code = "dlina"
        if category.parsed_name in mark_is_shirina:
            mark_code = "shirina-b"
        if category.parsed_name in mark_is_stenka:
            mark_code = "stenka"
        if category.parsed_name in mark_is_profil:
            mark_code = "profil"
        if category.parsed_name in mark_is_none:
            mark_code = ""
        else:
            mark_code = "marka-stali"

        if category.parsed_name in length_is_poverkhnost:
            length_code = "poverkhnost"
        else:
            length_code = "dlina"

        ProductPropertyValue.objects.update_or_create(
            product=product_instance,
            property=ProductProperty.objects.get(code=length_code),
            defaults={"value": product.length},
        )
        if mark_code:
            ProductPropertyValue.objects.update_or_create(
                product=product_instance,
                property=ProductProperty.objects.get(code=mark_code),
                defaults={"value": product.mark},
            )
        ProductPropertyValue.objects.update_or_create(
            product=product_instance,
            property=ProductProperty.objects.get(code=size_code),
            defaults={"value": product.size},
        )

    # Убираем отметку "В наличии" у продуктов, которые отсутствовали в
    # результатах парсинга
    Product.objects.filter(id__in=[prod.id for prod in category_products]).exclude(
        id__in=exist_in_parsed_products
    ).update(in_stock=False)
    # category_products.exclude(id__in=exist_in_parsed_products).update(in_stock=False)

    # парсим фильтры
    # parse_category_properties(soup)
    if len(parsed_products) > 0:
        category.is_parsing_successful = True
        category.save()

    result = f"Спаршено {len(parsed_products)} продуктов."
    result += f" Обновлено {instances_update_count} продуктов."
    result += f" Добавлено в БД {instances_create_count} продуктов."
    return result


@shared_task
def parse_weight(product_id: int):
    product = get_object_or_None(Product, id=product_id)

    if not product:
        return

    url = (
        "https://mc.ru/pages/blocks/add_basket.asp/id/"
        + f"{product.idt}/idf/{product.idf}/idb/{product.idb}"
    )

    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()

    except requests.exceptions.RequestException as e:
        logger.error("Error: {}", e)
        # return categories

    # lxml фэйлился на этой разметке...
    soup = BeautifulSoup(response.text, "lxml")
    script = soup.find("script", language="Javascript")
    # script = soup.find('script', text=re.compile('var k'))
    logger.debug("script: {}", script.text)
    # Получаем значение переменной
    k = re.search("var k=(.*?);", script.text)
    if k is None:
        logger.error("Не удалось Получить значение переменной")
        return "Regexp failed"
    found = k.group(1)
    weight = float(found) * 1000

    return weight

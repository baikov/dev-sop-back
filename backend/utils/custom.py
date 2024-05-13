import sys
import typing as t

import requests
from django.conf import settings
from django.core.cache import cache
from django.shortcuts import _get_queryset  # type: ignore
from loguru import logger as LOG

from backend.catalog.models import Category


def get_object_or_None(klass, *args, **kwargs):
    """
    Uses get() to return an object or None if the object does not exist.

    klass may be a Model, Manager, or QuerySet object. All other passed
    arguments and keyword arguments are used in the get() query.

    Note: Like with get(), a MultipleObjectsReturned will be raised if more than one
    object is found.
    """
    queryset = _get_queryset(klass)
    try:
        return queryset.get(*args, **kwargs)
    except queryset.model.DoesNotExist:
        return None


def create_breadcrumbs(
    obj: Category,
    root_path: str = "/catalog",
    disable_last: bool = True,
) -> list[dict]:
    if hasattr(obj, "parsed_name") and obj.name == "":
        obj.name = obj.parsed_name
    last_item = {
        "level": obj.depth,
        "name": obj.name,
        "href": f"{root_path}/{obj.slug}",
        "disabled": disable_last,
    }
    if obj.is_root():
        return [last_item]

    breadcrumbs = []
    for ancestor in obj.get_ancestors():
        if hasattr(ancestor, "parsed_name") and ancestor.name == "":
            ancestor.name = ancestor.parsed_name
        item = {
            "level": ancestor.depth,
            "name": ancestor.name,
            "href": f"{root_path}/{ancestor.slug}",
            "disabled": False,
        }
        breadcrumbs.append(item)
    breadcrumbs.append(last_item)

    return breadcrumbs


def query_yes_no(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
            It must be "yes" (the default), "no" or None (meaning
            an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == "":
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' " "(or 'y' or 'n').\n")


class TGeoInfo(t.TypedDict):
    ip: str
    country: str
    region: str
    city: str
    error: str


class GeoIP:
    _DOMAIN = "https://ru.sxgeo.city"
    _MAIN_TOKEN = "xyAsI"
    _DEBUG_IP = "176.115.148.81"

    def __init__(self):
        self._api_url = f"{self._DOMAIN}/{self._MAIN_TOKEN}/json"
        self._default_geo_info: TGeoInfo = {
            "ip": "Не определен",
            "country": "Не определена",
            "region": "Не определен",
            "city": "Не определен",
            "error": "",
        }

    @staticmethod
    def _ip_is_valid(ip: str) -> bool:
        """
        Check if IP is valid
        """
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        for part in parts:
            if not part.isdigit():
                return False
            if not 0 <= int(part) <= 255:
                return False
        return True

    def get_info(self, ip: str) -> TGeoInfo:
        if not self._ip_is_valid(ip):
            raise ValueError(f"Invalid IP: {ip}")
        if settings.DEBUG:
            ip = self._DEBUG_IP

        geo_info: TGeoInfo = cache.get(ip)
        if not geo_info:
            try:
                response = requests.get(f"{self._api_url}/{ip}")
                data = response.json()
            except Exception as e:
                self._default_geo_info["error"] = f"Request error: {e}"
                return self._default_geo_info

            if data.get("error"):
                self._default_geo_info["error"] = data.get("error")
                return self._default_geo_info

            city_obj = data.get("city")
            region_obj = data.get("region")
            country_obj = data.get("country")

            city = city_obj.get("name_ru", "Не определен") if city_obj else "Не определен"
            region = region_obj.get("name_ru", "Не определен") if region_obj else "Не определен"
            country = country_obj.get("name_ru", "Не определена") if country_obj else "Не определена"

            LOG.debug("check_geo_by_ip ip: {}", ip)
            geo_info = {
                "ip": ip,
                "country": country,
                "region": region,
                "city": city,
                "error": "",
            }

            if data.get("request") < 0:
                geo_info["error"] = f"Превышен лимит запросов в сервисе sypexgeo.net: {data.get('request')}"
                # return self._default_geo_info

            # Сохранить данные в кэш
            cache.set(ip, geo_info, 60 * 60 * 24 * 7)
            LOG.debug("Сохранено в кэш: {}", geo_info)

        return geo_info

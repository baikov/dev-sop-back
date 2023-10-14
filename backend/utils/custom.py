import sys

from django.shortcuts import _get_queryset  # type: ignore

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

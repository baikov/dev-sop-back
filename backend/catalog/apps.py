from django.apps import AppConfig


class ProductsConfig(AppConfig):
    name = "backend.catalog"

    def ready(self):
        try:
            import backend.catalog.signals  # noqa: F401
        except ImportError:
            pass

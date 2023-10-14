from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

from backend.catalog.views import (
    CategoryViewSet,
    ProductViewSet,
)

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()  # type: ignore

router.register("categories", CategoryViewSet, basename="categories")
router.register("products", ProductViewSet, basename="products")

app_name = "products"
urlpatterns = router.urls

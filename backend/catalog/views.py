import typing as t

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.viewsets import GenericViewSet

from backend.catalog.filters import ProductFilter
from backend.catalog.models import Category, FormSubmission, Product
from backend.catalog.pagination import LimitOffsetPagination
from backend.catalog.serializers import (
    CatalogLeftMenuSerializer,
    CatalogNewLeftMenuSerializer,
    CategoryDetailOutputSerializer,
    CategoryListOutputSerializer,
    CreateFormSubmissionSerializer,
    ProductDetailOutputSerializer,
    ProductListOutputSerializer,
    SitemapSerializer,
)
from backend.catalog.services.categories import (
    get_children_categories,
    get_root_categories,
)

# from backend.catalog.services.orders import create_form_submission
from backend.catalog.tasks import send_form_admin_email_task


class FormThrottle(ScopedRateThrottle):
    scope = "form"


class Pagination(LimitOffsetPagination):
    default_limit = 20


@extend_schema(tags=["Catalog"])
class ProductViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    """
    Вьюсет для получения товаров каталога
    """

    queryset = Product.objects.filter(is_published=True).prefetch_related("properties_through__property", "categories")
    serializer_class = ProductListOutputSerializer

    lookup_field = "slug"
    permission_classes = [AllowAny]
    filterset_class = ProductFilter
    filterset_fields = (
        "category",
        "gost",
        "diametr",
        "tolshina_stenki",
        "marka_stali",
        "vysota_h",
        "shirina_b",
        "dlina",
        "sort",
    )
    pagination_class = Pagination

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailOutputSerializer
        return self.serializer_class

    @action(methods=["GET"], detail=False)
    @method_decorator(cache_page(60 * 60 * 12))
    def sitemap(self, request):
        urls = Product.objects.filter(is_published=True, is_index=True).values("slug", "updated_date")
        data = SitemapSerializer(urls, many=True, context={"front_slug": "product"}).data

        return Response(data, status=status.HTTP_200_OK)


@extend_schema(tags=["Catalog"])
class CategoryViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    serializer_class = CategoryListOutputSerializer
    queryset = Category.objects.filter(is_published=True)
    lookup_field = "slug"
    permission_classes = [AllowAny]

    class Pagination(LimitOffsetPagination):
        default_limit = 20

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CategoryDetailOutputSerializer
        return self.serializer_class

    @action(methods=["GET"], detail=False)
    def root(self, request):
        root_categories = get_root_categories()
        serializer = self.get_serializer(root_categories, many=True)

        return Response(data=serializer.data, status=status.HTTP_200_OK)

    @action(methods=["GET"], detail=True)
    def children(self, request, slug=None):
        children_categories = get_children_categories(slug=slug)
        serializer = self.get_serializer(children_categories, many=True)

        return Response(data=serializer.data, status=status.HTTP_200_OK)

    @action(methods=["GET"], detail=False)
    def menu(self, request):
        items = get_root_categories().filter(is_published=True).order_by("ordering")
        data = CatalogLeftMenuSerializer(items, many=True).data

        return Response(data, status=status.HTTP_200_OK)

    @action(methods=["GET"], detail=False)
    def new_menu(self, request):
        data = Category.dump_bulk()
        data = CatalogNewLeftMenuSerializer(data, many=True).data

        return Response(data, status=status.HTTP_200_OK)

    @action(methods=["GET"], detail=False)
    @method_decorator(cache_page(60 * 60 * 12))
    def sitemap(self, request):
        urls = Category.objects.filter(is_published=True, is_index=True).values("slug", "updated_date")
        data = SitemapSerializer(urls, many=True, context={"front_slug": "catalog"}).data

        return Response(data, status=status.HTTP_200_OK)


class FormSubmissionViewSet(GenericViewSet, CreateModelMixin, RetrieveModelMixin):
    queryset = FormSubmission.objects.all()
    serializer_class = CreateFormSubmissionSerializer
    permission_classes = [AllowAny]
    throttle_classes = []
    throttle_scope = "form"

    def get_throttles(self):
        if self.action == "create":
            self.throttle_classes = [FormThrottle]

        return [throttle() for throttle in self.throttle_classes]

    def get_permissions(self) -> t.Sequence:
        if self.action == "retrieve":
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [AllowAny]  # type: ignore

        return [permission() for permission in permission_classes]

    def create(self, request: Request, *args: t.Any, **kwargs: t.Any) -> Response:
        product = request.data.pop("product")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        form = serializer.save()

        send_form_admin_email_task.delay(form.id, product)

        return Response(data=self.get_serializer(form).data, status=status.HTTP_201_CREATED)

    @action(methods=["GET"], detail=False, url_path="check-ip", permission_classes=[AllowAny])
    def check_ip(self, request):
        remote_addr = request.META.get("REMOTE_ADDR")
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        result = {
            "remote_addr": remote_addr,
            "forwarded": forwarded,
        }
        return Response(data=result, status=status.HTTP_200_OK)

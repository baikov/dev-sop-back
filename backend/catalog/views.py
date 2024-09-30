import typing as t

from celery import chain
from django.db.models import OuterRef, Q, Subquery
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
from backend.catalog.models import Category, Document, FormSubmission, Product, ProductCategories
from backend.catalog.pagination import LimitOffsetPagination
from backend.catalog.serializers import (
    CatalogLeftMenuSerializer,
    CatalogNewLeftMenuSerializer,
    CategoryDetailOutputSerializer,
    CategoryListOutputSerializer,
    CategoryYMLSerializer,
    CreateFormSubmissionSerializer,
    DocumentListSerializer,
    ProductDetailOutputSerializer,
    ProductListOutputSerializer,
    ProductYMLSerializer,
    SitemapSerializer,
    YMLSerializer,
)
from backend.catalog.services.categories import (
    get_children_categories,
    get_root_categories,
)
from backend.catalog.tasks import check_geo_by_ip_task, send_form_admin_email_task


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
        product = request.data.pop("product", None)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        form = serializer.save()

        remote_addr = request.META.get("REMOTE_ADDR")
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = forwarded if forwarded else remote_addr

        # send_form_admin_email_task.delay_on_commit(form.id, ip, product)
        chain(check_geo_by_ip_task.s(ip), send_form_admin_email_task.s(form.id, product))()

        return Response(data=self.get_serializer(form).data, status=status.HTTP_201_CREATED)

    @action(methods=["GET"], detail=False, url_path="check-ip", permission_classes=[AllowAny])
    def check_ip(self, request):
        remote_addr = request.META.get("REMOTE_ADDR")
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = forwarded if forwarded else remote_addr

        result = check_geo_by_ip_task.delay(ip)
        data = result.get()

        return Response(data=data, status=status.HTTP_200_OK)


class DocumentsViewSet(ListModelMixin, GenericViewSet):
    serializer_class = DocumentListSerializer
    queryset = Document.objects.filter(is_published=True).prefetch_related("categories")
    permission_classes = [AllowAny]


class YMLViewSet(GenericViewSet):
    permission_classes = [AllowAny]

    @extend_schema(responses=YMLSerializer)
    @method_decorator(cache_page(60 * 60 * 12))
    def list(self, request):
        primary_categories = ProductCategories.objects.filter(is_primary=True).values_list("category_id", flat=True)
        categories = Category.objects.filter(is_published=True, id__in=primary_categories)

        # Берем только товары, у которых есть цена и они опубликованы
        primary = ProductCategories.objects.filter(is_primary=True, product_id=OuterRef("id"))
        products = (
            Product.objects.annotate(
                prim=Subquery(primary.values("category_id")[:1]),
            )
            .filter(
                Q(unit_price__gt=0)
                | Q(ton_price__gt=0)
                | Q(meter_price__gt=0)
                | Q(custom_ton_price__gt=0)
                | Q(custom_unit_price__gt=0)
                | Q(custom_meter_price__gt=0),
                is_published=True,
                prim__isnull=False,
            )
            .distinct()
        )

        return Response(
            data={
                "categories": CategoryYMLSerializer(categories, many=True).data,
                "products": ProductYMLSerializer(products, many=True).data,
            },
            status=status.HTTP_200_OK,
        )

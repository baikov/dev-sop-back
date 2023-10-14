from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ViewSet

from backend.catalog.models import Category, Product
from backend.catalog.pagination import LimitOffsetPagination, get_paginated_response
from backend.catalog.serializers import (
    CatalogLeftMenuSerializer,
    CategoryDetailOutputSerializer,
    CategoryListOutputSerializer,
    ProductDetailOutputSerializer,
    ProductFilterSerializer,
    ProductListOutputSerializer,
)
from backend.catalog.services.categories import (
    get_category_product_list,
    get_children_categories,
    get_root_categories,
)
from backend.catalog.services.products import get_products_list
from backend.utils.custom import get_object_or_None


@extend_schema(tags=["Catalog"])
class ProductViewSet(ViewSet):
    """
    Вьюсет для получения товаров каталога
    """

    lookup_field = "slug"
    permission_classes = [AllowAny]

    def get_permissions(self):
        if self.action not in ("list", "retrieve"):
            permission_classes = [IsAdminUser]
        # else:
        #     permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="gost",
                description="Фильтр по ГОСТ",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="diametr",
                description="Фильтр по диаметру",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="thickness",
                description="Фильтр по толщине стенки",
                required=False,
                type=str,
            ),
        ],
        responses={
            200: ProductListOutputSerializer(many=True),
            400: OpenApiResponse(description="Переданы неверные параметры запроса"),
        },
    )
    def list(self, request):
        filters_serializer = ProductFilterSerializer(data=request.query_params)
        filters_serializer.is_valid(raise_exception=True)
        products = get_products_list(filters=filters_serializer.validated_data)
        data = ProductListOutputSerializer(products, many=True).data

        return Response(data, status=status.HTTP_200_OK)

    def retrieve(self, request, slug=None):
        qs = Product.objects.prefetch_related(
            "properties_through__property", "categories"
        )
        product = get_object_or_None(qs, slug=slug)
        data = ProductDetailOutputSerializer(product).data
        return Response(data)


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

    @action(methods=["GET"], detail=True)
    def products(self, request, slug=None):
        filters_serializer = ProductFilterSerializer(data=request.query_params)
        filters_serializer.is_valid(raise_exception=True)
        products = get_category_product_list(
            slug=slug, filters=filters_serializer.validated_data
        )
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=ProductListOutputSerializer,
            queryset=products,
            request=request,
            view=self,
        )

    @action(methods=["GET"], detail=False)
    def menu(self, request):
        items = get_root_categories().filter(is_published=True).order_by("ordering")
        data = CatalogLeftMenuSerializer(items, many=True).data

        return Response(data, status=status.HTTP_200_OK)

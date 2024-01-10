from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from backend.catalog.filters import ProductFilter
from backend.catalog.models import Category, Product
from backend.catalog.pagination import LimitOffsetPagination
from backend.catalog.serializers import (
    CatalogLeftMenuSerializer,
    CategoryDetailOutputSerializer,
    CategoryListOutputSerializer,
    ProductDetailOutputSerializer,
    ProductListOutputSerializer,
)
from backend.catalog.services.categories import (
    get_children_categories,
    get_root_categories,
)


class Pagination(LimitOffsetPagination):
    default_limit = 20


@extend_schema(tags=["Catalog"])
class ProductViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    """
    Вьюсет для получения товаров каталога
    """

    queryset = Product.objects.prefetch_related(
        "properties_through__property", "categories"
    )
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

    # @action(methods=["GET"], detail=True)
    # def products(self, request, slug=None):
    #     filters_serializer = ProductFilterSerializer(data=request.query_params)
    #     filters_serializer.is_valid(raise_exception=True)
    #     products = get_category_product_list(
    #         slug=slug, filters=filters_serializer.validated_data
    #     )
    #     return get_paginated_response(
    #         pagination_class=self.Pagination,
    #         serializer_class=ProductListOutputSerializer,
    #         queryset=products,
    #         request=request,
    #         view=self,
    #     )

    @action(methods=["GET"], detail=False)
    def menu(self, request):
        items = get_root_categories().filter(is_published=True).order_by("ordering")
        data = CatalogLeftMenuSerializer(items, many=True).data

        return Response(data, status=status.HTTP_200_OK)

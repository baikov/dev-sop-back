import logging

# import smtplib
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage, get_connection

# from loguru import logger as LOG
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from .serializers import CustomUserDetailsSerializer

logger = logging.getLogger(__name__)

User = get_user_model()


class UserViewSet(ListModelMixin, GenericViewSet):
    serializer_class = CustomUserDetailsSerializer
    queryset = User.objects.all()
    lookup_field = "username"
    permission_classes = (IsAdminUser,)


class MailView(APIView):
    def post(self, request):
        # LOG.debug("settings.EMAIL_HOST: {}", settings.EMAIL_HOST)
        # LOG.debug("settings.EMAIL_PORT: {}", settings.EMAIL_PORT)
        # LOG.debug("settings.EMAIL_HOST_USER: {}", settings.EMAIL_HOST_USER)
        # LOG.debug("settings.EMAIL_HOST_PASSWORD: {}", settings.EMAIL_HOST_PASSWORD)
        # LOG.debug("settings.EMAIL_USE_TLS: {}", settings.EMAIL_USE_TLS)
        # LOG.debug("settings.EMAIL_USE_SSL: {}", settings.EMAIL_USE_SSL)
        # # check smtp connection
        # server = smtplib.SMTP_SSL("smtp.yandex.ru:465")
        # try:
        #     server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        #     LOG.debug("SMTP connection successful")
        # except Exception as e:
        #     LOG.error("SMTP connection failed: {}", e)
        # server.quit()

        with get_connection(
            host=settings.EMAIL_HOST,
            port=settings.EMAIL_PORT,
            username=settings.EMAIL_HOST_USER,
            password=settings.EMAIL_HOST_PASSWORD,
            use_tls=settings.EMAIL_USE_TLS,
            use_ssl=settings.EMAIL_USE_SSL,
        ) as connection:
            subject = "Test Email"
            email_from = settings.EMAIL_HOST_USER
            recipient_list = [
                request.data.get("email"),
            ]
            message = "This is a test email"
            try:
                EmailMessage(subject, message, email_from, recipient_list, connection=connection).send()
                return Response("OK", status=200)
            except Exception as e:
                logger.error(e)

        return Response("Bad", status=400)

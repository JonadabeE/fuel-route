from django.urls import path
from .views import calculate_route
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('calculate_route/', calculate_route, name='calculate_route'),  # A URL sem o prefixo 'api/'
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

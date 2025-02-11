
from django.contrib import admin
from django.urls import path
from api.views import calculate_route

urlpatterns = [
    path('admin/', admin.site.urls),
     path('calculate_route/', calculate_route, name='calculate_route'),
]

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("comptes/", include("comptes.urls")),
    path("referentiel/", include("referentiel.urls")),
    path("", include("depannages.urls")),
]

if settings.URL_PREFIX:
    urlpatterns = [path(f"{settings.URL_PREFIX}/", include(urlpatterns))]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Gestion des depannages"
admin.site.site_title = "Gestion des depannages"
admin.site.index_title = "Administration"

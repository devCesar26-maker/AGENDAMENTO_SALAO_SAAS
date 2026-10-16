from csp.decorators import csp_exempt
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    # csp_exempt: o template do Swagger UI usa <script>/<style> inline, que a
    # CSP restritiva (script/style-src 'self') bloqueia e deixa a página em
    # branco. Somente estas URLs de documentação ficam fora da CSP; o restante
    # do site mantém a política. Os assets do Swagger UI passam a ser servidos
    # localmente via drf-spectacular-sidecar ("SWAGGER_UI_DIST": "SIDECAR" em
    # settings/base.py), sem depender de CDN.
    path(
        "api/docs/",
        csp_exempt()(SpectacularSwaggerView.as_view(url_name="api-schema")),
        name="api-docs",
    ),
    path("api/v1/", include("core.urls")),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("organizations.urls")),
    path("api/v1/", include("catalog.urls")),
    path("api/v1/", include("customers.urls")),
]

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns = [path("__debug__/", include(debug_toolbar.urls)), *urlpatterns]

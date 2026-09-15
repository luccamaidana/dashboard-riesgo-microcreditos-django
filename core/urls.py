# core/urls.py

from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # APIs internas simuladas (representan servicios externos)
    path('api/score/<str:solicitud_id>/', views.api_score, name='api_score'),
    path('api/mora/<str:solicitud_id>/', views.api_mora, name='api_mora'),
    path('api/identidad/<str:solicitud_id>/', views.api_identidad, name='api_identidad'),

    # Dashboard de riesgo
    path('riesgo/solicitudes/<str:solicitud_id>/', views.dashboard_riesgo, name='dashboard_riesgo'),
    path('riesgo/solicitudes/<str:solicitud_id>/refresh/', views.dashboard_riesgo_refresh, name='dashboard_riesgo_refresh'),
]
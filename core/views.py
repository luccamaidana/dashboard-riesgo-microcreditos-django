# core/views.py

import json
import random
import time
import urllib.request
import urllib.error
from urllib.parse import quote

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from .models import Solicitud


# ============================================================
# APIs internas simuladas.
# Representan conceptualmente servicios externos: no importan ni
# consultan el modelo Solicitud, no persisten nada, y cada una puede
# fallar o demorar de forma independiente.
# ============================================================

TIMEOUT_SIMULADO_SEGUNDOS = 3
PROBABILIDAD_ERROR = 0.15
PROBABILIDAD_TIMEOUT = 0.10


def _semilla_por_solicitud(solicitud_id):
    """
    Semilla determinística a partir del id, para que las respuestas
    simuladas sean reproducibles por solicitud (la misma solicitud
    siempre tiende a dar el mismo score, no un valor random distinto
    en cada llamada), sin necesidad de persistir nada.
    """
    return random.Random(solicitud_id)


@require_GET
def api_score(request, solicitud_id):
    """
    GET /api/score/<solicitud_id>/
    Simula un motor de scoring crediticio externo.
    """
    rnd = _semilla_por_solicitud(f"score-{solicitud_id}")

    if rnd.random() < PROBABILIDAD_TIMEOUT:
        time.sleep(TIMEOUT_SIMULADO_SEGUNDOS + 1)

    if rnd.random() < PROBABILIDAD_ERROR:
        return JsonResponse(
            {'error': 'Servicio de scoring no disponible.'},
            status=503,
        )

    score = rnd.randint(300, 850)
    if score < 500:
        categoria = 'alto'
    elif score < 700:
        categoria = 'medio'
    else:
        categoria = 'bajo'

    return JsonResponse({
        'solicitud_id': solicitud_id,
        'score': score,
        'categoria_riesgo': categoria,
    })


@require_GET
def api_mora(request, solicitud_id):
    """
    GET /api/mora/<solicitud_id>/
    Simula un servicio de historial de atrasos de pago.
    """
    rnd = _semilla_por_solicitud(f"mora-{solicitud_id}")

    if rnd.random() < PROBABILIDAD_TIMEOUT:
        time.sleep(TIMEOUT_SIMULADO_SEGUNDOS + 1)

    if rnd.random() < PROBABILIDAD_ERROR:
        return JsonResponse(
            {'error': 'Servicio de mora no disponible.'},
            status=503,
        )

    dias_atraso = rnd.choice([0, 0, 0, 5, 12, 30, 45])

    return JsonResponse({
        'solicitud_id': solicitud_id,
        'dias_atraso': dias_atraso,
        'tiene_atrasos': dias_atraso > 0,
    })


@require_GET
def api_identidad(request, solicitud_id):
    """
    GET /api/identidad/<solicitud_id>/
    Simula un servicio de validación básica de identidad.
    """
    rnd = _semilla_por_solicitud(f"identidad-{solicitud_id}")

    if rnd.random() < PROBABILIDAD_TIMEOUT:
        time.sleep(TIMEOUT_SIMULADO_SEGUNDOS + 1)

    if rnd.random() < PROBABILIDAD_ERROR:
        return JsonResponse(
            {'error': 'Servicio de identidad no disponible.'},
            status=503,
        )

    validada = rnd.random() > 0.2

    return JsonResponse({
        'solicitud_id': solicitud_id,
        'identidad_validada': validada,
        'metodo_validacion': rnd.choice(['documento', 'biometria', 'referencia_cruzada']),
    })


# ============================================================
# Cliente HTTP para consumir las APIs internas desde el dashboard.
# Usa urllib (librería estándar, sin dependencias externas) y parsea
# el JSON manualmente con json.loads, como pide el enunciado.
# ============================================================

def _consultar_fuente(url, timeout=2):
    """
    Ejecuta un GET aislado contra una fuente y devuelve un resultado
    uniforme, sin importar si la fuente respondió bien, con error, o
    no respondió a tiempo. Nunca lanza una excepción hacia arriba:
    una falla en una fuente no debe interrumpir el renderizado de las
    demás (requisito explícito del enunciado).
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            cuerpo = response.read().decode('utf-8')
            datos = json.loads(cuerpo)
            return {
                'disponible': True,
                'datos': datos,
                'error': None,
            }

    except urllib.error.HTTPError as error:
        try:
            cuerpo_error = json.loads(error.read().decode('utf-8'))
            mensaje = cuerpo_error.get('error', f'Error HTTP {error.code}')
        except (json.JSONDecodeError, AttributeError):
            mensaje = f'Error HTTP {error.code}'
        return {'disponible': False, 'datos': None, 'error': mensaje}

    except urllib.error.URLError:
        return {'disponible': False, 'datos': None, 'error': 'No se pudo conectar con el servicio.'}

    except TimeoutError:
        return {'disponible': False, 'datos': None, 'error': 'El servicio no respondió a tiempo.'}

    except json.JSONDecodeError:
        return {'disponible': False, 'datos': None, 'error': 'La respuesta del servicio no es JSON válido.'}


def _construir_contexto_riesgo(request, solicitud_id):
    """
    Consulta las 3 fuentes de forma aislada (una falla no afecta a las
    otras) y arma el diccionario que va a consumir el template.
    Cada fuente se resuelve por separado, en orden secuencial: no se
    usan hilos ni async, coherente con "no usar librerías externas" y
    mantener la implementación simple con la librería estándar.
    """
    id_url = quote(str(solicitud_id))

    url_score = request.build_absolute_uri(reverse('core:api_score', args=[id_url]))
    url_mora = request.build_absolute_uri(reverse('core:api_mora', args=[id_url]))
    url_identidad = request.build_absolute_uri(reverse('core:api_identidad', args=[id_url]))

    return {
        'score': _consultar_fuente(url_score),
        'mora': _consultar_fuente(url_mora),
        'identidad': _consultar_fuente(url_identidad),
    }


# ============================================================
# Dashboard de riesgo.
# ============================================================

def _renderizar_dashboard(request, solicitud_id):
    """
    Lógica compartida entre el dashboard normal y el de refresh:
    busca la solicitud, consulta las 3 fuentes y renderiza. Se separó
    en una función aparte para no duplicar este bloque entre las dos
    views (GET /riesgo/solicitudes/<id>/ y .../refresh/).
    """
    try:
        solicitud = Solicitud.objects.get(identificador=solicitud_id)
    except Solicitud.DoesNotExist:
        contexto = {
            'solicitud_id': solicitud_id,
            'solicitud': None,
            'error_solicitud': f"No existe una solicitud con identificador '{solicitud_id}'.",
        }
        return render(request, 'core/dashboard_riesgo.html', contexto, status=404)

    fuentes = _construir_contexto_riesgo(request, solicitud_id)

    contexto = {
        'solicitud_id': solicitud_id,
        'solicitud': solicitud,
        'error_solicitud': None,
        'fuentes': fuentes,
    }
    return render(request, 'core/dashboard_riesgo.html', contexto)


@require_GET
def dashboard_riesgo(request, solicitud_id):
    """GET /riesgo/solicitudes/<id>/"""
    return _renderizar_dashboard(request, solicitud_id)


@require_GET
def dashboard_riesgo_refresh(request, solicitud_id):
    """
    GET /riesgo/solicitudes/<id>/refresh/
    Reejecuta las 3 consultas (nunca hay caché de por medio, así que
    en la práctica es idéntico a la view principal) y vuelve a
    renderizar. Se mantiene como endpoint separado, tal como lo pide
    el enunciado, para que el operador tenga una acción explícita de
    "actualizar" en la pantalla.
    """
    return _renderizar_dashboard(request, solicitud_id)
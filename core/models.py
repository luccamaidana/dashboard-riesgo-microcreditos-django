# core/models.py

from django.db import models


class Solicitud(models.Model):
    """
    Solicitud de crédito ya registrada en el sistema. Es la única
    entidad persistida de este dominio: los indicadores de riesgo
    (score, mora, identidad) NO viven acá, se consultan en vivo a
    APIs internas simuladas y nunca se guardan (así lo exige el
    enunciado: "no se persisten respuestas externas").

    Ese aislamiento es intencional: este modelo no sabe nada de riesgo,
    y los endpoints de riesgo (/api/score/, /api/mora/, /api/identidad/)
    no van a importar ni consultar este modelo — operan sobre el
    solicitud_id como un dato opaco, sin tocar el dominio de solicitudes.
    """

    class Estado(models.TextChoices):
        PENDIENTE_REVISION = 'pendiente_revision', 'Pendiente de revisión'
        EN_REVISION = 'en_revision', 'En revisión'
        APROBADA = 'aprobada', 'Aprobada'
        RECHAZADA = 'rechazada', 'Rechazada'

    identificador = models.CharField(
        max_length=40,
        unique=True,
        help_text="Identificador público de la solicitud, ej: SOL-00812"
    )
    nombre_solicitante = models.CharField(max_length=150)
    monto_solicitado = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE_REVISION,
    )
    fecha_solicitud = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Solicitud de crédito"
        verbose_name_plural = "Solicitudes de crédito"
        ordering = ['-fecha_solicitud']
        indexes = [
            models.Index(fields=['identificador']),
        ]

    def __str__(self):
        return f"{self.identificador} - {self.nombre_solicitante}"
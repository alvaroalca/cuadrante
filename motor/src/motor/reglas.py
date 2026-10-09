"""Esquema cerrado de reglas de un convenio y mínimos del Estatuto de los Trabajadores.

Solo entran los tipos que cambian un cuadrante mensual. Lo demás (salarios, permisos,
pausas que cuentan como tiempo efectivo) se queda fuera o va como `otra`, que se
enseña para revisión y el solver no aplica.

El agente lector-convenio rellena `ReglasConvenio`; este módulo comprueba la forma.
Que la cita exista y contenga la cifra lo comprueba el validador, no el esquema.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TipoRegla(StrEnum):
    JORNADA_ANUAL_MAX = "jornada_anual_max"
    HORAS_SEMANA_PROMEDIO_MAX = "horas_semana_promedio_max"
    HORAS_SEMANA_TOPE = "horas_semana_tope"
    HORAS_DIA_MAX = "horas_dia_max"
    DESCANSO_ENTRE_JORNADAS_MIN = "descanso_entre_jornadas_min"
    DESCANSO_SEMANAL_MIN = "descanso_semanal_min"
    DIAS_LIBRES_MIN_EN_VENTANA = "dias_libres_min_en_ventana"
    DIAS_CONSECUTIVOS_MAX = "dias_consecutivos_max"
    FINES_SEMANA_LIBRES_MIN = "fines_semana_libres_min"
    DOMINGOS_LIBRES_MIN = "domingos_libres_min"
    DOMINGOS_FESTIVOS_TRABAJO_MAX = "domingos_festivos_trabajo_max"
    DESCANSO_COMPENSATORIO_FESTIVO = "descanso_compensatorio_festivo"
    HORAS_NOCHE_PROMEDIO_MAX = "horas_noche_promedio_max"
    TURNO_BANDA = "turno_banda"
    PAUSA_JORNADA_PARTIDA = "pausa_jornada_partida"
    REPLANIFICACION_MAX_PLANTILLA = "replanificacion_max_plantilla"
    PREAVISO_CAMBIO_MIN = "preaviso_cambio_min"
    COMPLEMENTARIAS_PACTADAS_MAX_PCT = "complementarias_pactadas_max_pct"
    COMPLEMENTARIAS_VOLUNTARIAS_MAX_PCT = "complementarias_voluntarias_max_pct"
    PREAVISO_COMPLEMENTARIAS_MIN = "preaviso_complementarias_min"
    OTRA = "otra"


# Significado de cada tipo. Va dentro del esquema que lee el agente: con el nombre solo,
# "3 días de descanso en 14" acababa en descanso_semanal_min en vez de en la ventana.
DESCRIPCION = {
    TipoRegla.JORNADA_ANUAL_MAX: "Horas máximas de trabajo efectivo al año.",
    TipoRegla.HORAS_SEMANA_PROMEDIO_MAX: "Horas semanales máximas de promedio (la jornada ordinaria semanal).",
    TipoRegla.HORAS_SEMANA_TOPE: "Horas máximas en una semana concreta, aunque el promedio se cumpla.",
    TipoRegla.HORAS_DIA_MAX: "Horas máximas de trabajo en un día.",
    TipoRegla.DESCANSO_ENTRE_JORNADAS_MIN: "Horas mínimas entre el final de una jornada y el comienzo de la siguiente.",
    TipoRegla.DESCANSO_SEMANAL_MIN: "Descanso ininterrumpido POR SEMANA (p. ej. día y medio). Si el texto permite acumularlo, periodo 'ventana' y ventana_dias = días de acumulación, pero valor sigue siendo lo de una semana. Si el texto da el total del periodo ('tres días en catorce'), no es este tipo: es dias_libres_min_en_ventana.",
    TipoRegla.DIAS_LIBRES_MIN_EN_VENTANA: "Número mínimo de días libres dentro de cada periodo de N días (p. ej. 3 en 14, 1 en 7). periodo 'ventana' y ventana_dias = N.",
    TipoRegla.DIAS_CONSECUTIVOS_MAX: "Días seguidos máximos de trabajo sin descanso.",
    TipoRegla.FINES_SEMANA_LIBRES_MIN: "Fines de semana completos (sábado y domingo) libres como mínimo, por mes o por año.",
    TipoRegla.DOMINGOS_LIBRES_MIN: "Domingos libres como mínimo en un periodo (p. ej. 1 cada 4 semanas: valor 1, periodo 'ventana', ventana_dias 28).",
    TipoRegla.DOMINGOS_FESTIVOS_TRABAJO_MAX: "Domingos y festivos trabajados como máximo en un periodo.",
    TipoRegla.DESCANSO_COMPENSATORIO_FESTIVO: "Días libres que genera cada festivo trabajado.",
    TipoRegla.HORAS_NOCHE_PROMEDIO_MAX: "Horas diarias de promedio máximas en trabajo nocturno, en una ventana de N días.",
    TipoRegla.TURNO_BANDA: "Hora más temprana de entrada y más tardía de salida de un turno (turno, desde, hasta).",
    TipoRegla.PAUSA_JORNADA_PARTIDA: "Horas de interrupción en la jornada partida: valor = mínimo, valor_max = máximo. Basta con uno de los dos.",
    TipoRegla.REPLANIFICACION_MAX_PLANTILLA: "Porcentaje máximo de la plantilla al que se le puede cambiar el horario ya publicado.",
    TipoRegla.PREAVISO_CAMBIO_MIN: "Días mínimos de antelación para publicar o cambiar un horario.",
    TipoRegla.COMPLEMENTARIAS_PACTADAS_MAX_PCT: "Tiempo parcial: horas complementarias pactadas máximas, en % de las horas ordinarias del contrato.",
    TipoRegla.COMPLEMENTARIAS_VOLUNTARIAS_MAX_PCT: "Tiempo parcial: horas complementarias de aceptación voluntaria máximas, en % de las horas ordinarias del contrato.",
    TipoRegla.PREAVISO_COMPLEMENTARIAS_MIN: "Días mínimos de preaviso para exigir horas complementarias pactadas.",
    TipoRegla.OTRA: "Escape: restricción de horario que no encaja en ningún tipo. Necesita descripcion. Se enseña para revisión y el solver no la aplica.",
}


Unidad = Literal["horas", "dias", "veces", "porcentaje"]
Periodo = Literal["dia", "semana", "mes", "año", "ventana"]
Turno = Literal["mañana", "tarde", "noche", "partido"]


class Cita(BaseModel):
    articulo: str = Field(description='Número tal como sale en el encabezado, con apartado si lo hay: "30.3", "22"')
    texto: str = Field(description="Fragmento literal del artículo del que sale la regla")


class Regla(BaseModel):
    tipo: TipoRegla = Field(description="; ".join(f"{t.value}: {d}" for t, d in DESCRIPCION.items()))
    valor: float | None = None
    valor_max: float | None = None
    unidad: Unidad | None = None
    periodo: Periodo | None = None
    ventana_dias: int | None = None
    turno: Turno | None = None
    desde: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    hasta: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    condicion: str | None = Field(None, description="Solo si la regla aplica únicamente en un caso (zona, ámbito, tipo de empresa). null = regla general. Una regla general con salvedad no lleva condicion: lleva excepto")
    excepto: str | None = Field(None, description="A quién no se aplica una regla general ('excepto contratos de fin de semana'). La regla sigue siendo general y el solver la aplica a todos los demás")
    vigente_desde: int | None = Field(None, description="Año desde el que aplica, si el convenio escalona")
    descripcion: str | None = Field(None, description="Obligatoria en 'otra'; opcional en el resto")
    pactable: Literal["individual", "colectivo", "no"] = Field(
        "no",
        description="Si el propio texto permite apartarse de la regla por acuerdo y de qué tipo. "
        "Sin mención expresa es 'no': un contrato no puede empeorar el convenio (ET 3.1.c)",
    )
    cita: Cita
    cita_pacto: Cita | None = Field(None, description="Obligatoria si pactable no es 'no': la frase que permite el acuerdo")
    origen: Literal["convenio", "estatuto"] = "convenio"

    @model_validator(mode="after")
    def forma_por_tipo(self) -> "Regla":
        if self.pactable != "no" and self.cita_pacto is None:
            raise ValueError("una regla pactable necesita cita_pacto")
        t = self.tipo
        if t == TipoRegla.OTRA:
            if not self.descripcion:
                raise ValueError("'otra' necesita descripcion")
            return self
        if t == TipoRegla.TURNO_BANDA:
            if not (self.turno and self.desde and self.hasta):
                raise ValueError("turno_banda necesita turno, desde y hasta")
            return self
        if t == TipoRegla.PAUSA_JORNADA_PARTIDA:
            if self.valor is None and self.valor_max is None:
                raise ValueError("pausa_jornada_partida necesita valor, valor_max o los dos")
        elif self.valor is None:
            raise ValueError(f"{t} necesita valor")
        if self.periodo == "ventana" and not self.ventana_dias:
            raise ValueError("periodo 'ventana' necesita ventana_dias")
        return self


class ReglasConvenio(BaseModel):
    boe: str = Field(pattern=r"^BOE-A-\d{4}-\d+$")
    nombre: str
    reglas: list[Regla]


# Mínimos del Estatuto (RDL 2/2015), texto consolidado del BOE (BOE-A-2015-11430).
# Se aplican cuando el convenio no trae una regla del mismo tipo. Son derecho necesario:
# ni con el acuerdo de la persona se puede bajar de ellos.
NO_DISPONIBLE = Cita(articulo="ET 3.5", texto="Los trabajadores no podrán disponer válidamente, antes o después de su adquisición, de los derechos que tengan reconocidos por disposiciones legales de derecho necesario.")

# Franja nocturna del ET 36.1: de 22:00 a 06:00.
NOCHE_DESDE, NOCHE_HASTA = 22, 6
NOCHE_CITA = Cita(articulo="ET 36.1", texto="se considera trabajo nocturno el realizado entre las diez de la noche y las seis de la mañana")

ESTATUTO = [
    Regla(
        tipo=TipoRegla.HORAS_SEMANA_PROMEDIO_MAX, valor=40, unidad="horas", periodo="semana",
        origen="estatuto",
        cita=Cita(articulo="ET 34.1", texto="La duración máxima de la jornada ordinaria de trabajo será de cuarenta horas semanales de trabajo efectivo de promedio en cómputo anual."),
    ),
    Regla(
        tipo=TipoRegla.DESCANSO_ENTRE_JORNADAS_MIN, valor=12, unidad="horas",
        origen="estatuto",
        cita=Cita(articulo="ET 34.3", texto="Entre el final de una jornada y el comienzo de la siguiente mediarán, como mínimo, doce horas."),
    ),
    Regla(
        tipo=TipoRegla.HORAS_DIA_MAX, valor=9, unidad="horas", periodo="dia",
        origen="estatuto",
        cita=Cita(articulo="ET 34.3", texto="El número de horas ordinarias de trabajo efectivo no podrá ser superior a nueve diarias"),
    ),
    Regla(
        tipo=TipoRegla.DESCANSO_SEMANAL_MIN, valor=1.5, unidad="dias", periodo="ventana", ventana_dias=14,
        origen="estatuto",
        cita=Cita(articulo="ET 37.1", texto="Los trabajadores tendrán derecho a un descanso mínimo semanal, acumulable por periodos de hasta catorce días, de día y medio ininterrumpido"),
    ),
    Regla(
        tipo=TipoRegla.HORAS_NOCHE_PROMEDIO_MAX, valor=8, unidad="horas", periodo="ventana", ventana_dias=15,
        origen="estatuto",
        cita=Cita(articulo="ET 36.1", texto="La jornada de trabajo de los trabajadores nocturnos no podrá exceder de ocho horas diarias de promedio, en un periodo de referencia de quince días."),
    ),
    Regla(
        tipo=TipoRegla.COMPLEMENTARIAS_PACTADAS_MAX_PCT, valor=30, unidad="porcentaje",
        origen="estatuto",
        cita=Cita(articulo="ET 12.5.c", texto="El número de horas complementarias pactadas no podrá exceder del treinta por ciento de las horas ordinarias de trabajo objeto del contrato."),
    ),
    Regla(
        tipo=TipoRegla.COMPLEMENTARIAS_VOLUNTARIAS_MAX_PCT, valor=15, unidad="porcentaje",
        origen="estatuto",
        cita=Cita(articulo="ET 12.5.g", texto="cuyo número no podrá superar el quince por ciento, ampliables al treinta por ciento por convenio colectivo, de las horas ordinarias objeto del contrato"),
    ),
    Regla(
        tipo=TipoRegla.PREAVISO_COMPLEMENTARIAS_MIN, valor=3, unidad="dias",
        origen="estatuto",
        cita=Cita(articulo="ET 12.5.d", texto="El trabajador deberá conocer el día y la hora de realización de las horas complementarias pactadas con un preaviso mínimo de tres días"),
    ),
    Regla(
        tipo=TipoRegla.PREAVISO_CAMBIO_MIN, valor=5, unidad="dias",
        condicion="cambios por distribución irregular de la jornada",
        origen="estatuto",
        cita=Cita(articulo="ET 34.2", texto="el trabajador deberá conocer con un preaviso mínimo de cinco días el día y la hora de la prestación de trabajo resultante de aquella"),
    ),
]


def efectivas(convenio: ReglasConvenio, año: int, condiciones: set[str] = frozenset()) -> list[Regla]:
    """Reglas que aplica el solver en `año`.

    Del convenio, las generales vigentes ese año y las condicionadas cuya condición
    está en `condiciones` (la ficha de empresa copia el texto literal del JSON). Para un
    mismo tipo gana la condicionada activa sobre la general, y entre escalones el más
    reciente. Del Estatuto, los tipos que el convenio no trae: si el convenio regula un
    tipo, su regla sustituye a la del Estatuto.
    (El preaviso del ET 34.2 es de la distribución irregular y lleva condición; aplicarlo
    a todo bloquearía replanificar una baja, que p. ej. grandes almacenes 27.3 permite.)
    """
    elegidas: dict[tuple, Regla] = {}
    prioridad = lambda r: (r.condicion is not None, r.vigente_desde or 0)
    for r in convenio.reglas:
        if r.tipo == TipoRegla.OTRA:
            continue
        if r.condicion is not None and r.condicion not in condiciones:
            continue
        if r.vigente_desde is not None and r.vigente_desde > año:
            continue
        clave = (r.tipo, r.turno)
        if clave not in elegidas or prioridad(r) > prioridad(elegidas[clave]):
            elegidas[clave] = r
    tipos = {t for t, _ in elegidas}
    return list(elegidas.values()) + [r for r in ESTATUTO if r.tipo not in tipos and r.condicion is None]

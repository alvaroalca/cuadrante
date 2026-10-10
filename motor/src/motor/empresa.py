"""Ficha de empresa y el contexto que comparten el solver y el comprobador.

La ficha (demo/empresa.json) dice el horario de apertura, cuánta gente hace falta cada
hora, quién trabaja y con qué contrato, las ausencias y qué condiciones de cada convenio
cumple la empresa. `Contexto` junta eso con las reglas efectivas del convenio elegido.

Un turno es (inicio, fin) en horas enteras del día; fin > 24 si cruza la medianoche.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from motor.reglas import Regla, ReglasConvenio, TipoRegla, efectivas

RAIZ = Path(__file__).resolve().parents[3]

Turno = tuple[int, int]


def horas(t: Turno) -> int:
    return t[1] - t[0]


def hora(texto: str) -> float:
    h, m = texto.split(":")
    return int(h) + int(m) / 60


class Franja(BaseModel):
    desde: int
    hasta: int
    personas: int


class Persona(BaseModel):
    nombre: str
    horas_semana: int | Literal["completa"]
    indefinido: bool = True
    pacto_complementarias_pct: int = Field(0, ge=0, le=100)
    saldo_horas: int = 0  # en lo que va de año: + ha trabajado de más, - debe horas

    @property
    def parcial(self) -> bool:
        return self.horas_semana != "completa"


class Ausencia(BaseModel):
    persona: str
    fecha: date
    desde: int | None = None  # sin horas = el día entero
    hasta: int | None = None
    motivo: str = ""
    aviso: date | None = None  # cuándo se entera la empresa; sin fecha, el día anterior
    imprevista: bool = True


class Acuerdo(BaseModel):
    """Acuerdo de una persona para una edición a mano que se salta una regla pactable a
    título individual. Cubre justo los incumplimientos que se le enseñaron: si una edición
    posterior los cambia, hay que volver a pedírselo."""
    persona: str
    tipo: str
    dias: list[int] = []
    mensaje: str


class Periodo(BaseModel):
    inicio: date
    dias: int


class Rango(BaseModel):
    desde: int
    hasta: int


class Empresa(BaseModel):
    nombre: str
    periodo: Periodo
    festivos: list[date] = []
    vacaciones_dias_naturales: int = 30
    festivos_anuales: int = 14
    apertura: Rango
    turno_horas: list[int]  # duraciones posibles de un turno, en horas
    # Lo obligatorio es la jornada anual: semanas y periodos se desvían y la diferencia va
    # al saldo de cada persona. Estos márgenes son política de la empresa, no del convenio:
    # cuánto puede alejarse una semana del contrato y el periodo de su objetivo.
    margen_semanal_horas: int = 10
    margen_periodo_horas: int = 8
    cobertura: dict[Literal["laborable", "sabado", "domingo"], list[Franja]]
    plantilla: list[Persona]
    ausencias: list[Ausencia] = []
    condiciones: dict[str, list[str]] = {}
    # Condiciones de reglas del convenio que se cumplen cuando una ausencia es imprevista
    # (p. ej. el preaviso de 48 h de dependencia, art. 18.6). Texto literal del JSON.
    condiciones_imprevistas: dict[str, list[str]] = {}


def cargar_empresa(ruta: Path = RAIZ / "demo" / "empresa.json") -> Empresa:
    return Empresa.model_validate_json(ruta.read_text(encoding="utf-8"))


def cargar_convenio(boe_id: str) -> ReglasConvenio:
    return ReglasConvenio.model_validate_json((RAIZ / "reglas" / f"{boe_id}.json").read_text(encoding="utf-8"))


@dataclass
class Contexto:
    empresa: Empresa
    convenio: ReglasConvenio
    reglas: list[Regla]

    @classmethod
    def crear(cls, empresa: Empresa, convenio: ReglasConvenio) -> "Contexto":
        condiciones = set(empresa.condiciones.get(convenio.boe, []))
        reglas = efectivas(convenio, empresa.periodo.inicio.year, condiciones)
        return cls(empresa, convenio, reglas)

    # --- Calendario ---

    @property
    def fechas(self) -> list[date]:
        p = self.empresa.periodo
        return [p.inicio + timedelta(days=i) for i in range(p.dias)]

    @property
    def n_dias(self) -> int:
        return self.empresa.periodo.dias

    def es_festivo(self, d: int) -> bool:
        return self.fechas[d] in self.empresa.festivos

    def es_domingo_o_festivo(self, d: int) -> bool:
        return self.fechas[d].weekday() == 6 or self.es_festivo(d)

    def semanas(self) -> list[list[int]]:
        """Semanas de lunes a domingo enteras dentro del periodo."""
        return [list(range(d, d + 7)) for d, f in enumerate(self.fechas) if f.weekday() == 0 and d + 7 <= self.n_dias]

    def ventanas(self, largo: int) -> list[list[int]]:
        """Ventanas deslizantes de `largo` días enteras dentro del periodo."""
        return [list(range(d, d + largo)) for d in range(self.n_dias - largo + 1)]

    def fines_de_semana(self) -> list[tuple[int, int]]:
        return [(d, d + 1) for d, f in enumerate(self.fechas) if f.weekday() == 5 and d + 1 < self.n_dias]

    def domingos(self) -> list[int]:
        return [d for d, f in enumerate(self.fechas) if f.weekday() == 6]

    def necesidad(self, d: int, h: int) -> int:
        """Personas que hacen falta el día d a la hora h (de h a h+1)."""
        dia = self.fechas[d].weekday()
        clave = "domingo" if dia == 6 or self.es_festivo(d) else "sabado" if dia == 5 else "laborable"
        return sum(f.personas for f in self.empresa.cobertura[clave] if f.desde <= h < f.hasta)

    # --- Turnos ---

    def catalogo(self) -> list[Turno]:
        """Turnos posibles: bloques continuos de horas enteras dentro de la apertura."""
        a = self.empresa.apertura
        return [(i, i + n) for i in range(a.desde, a.hasta) for n in self.empresa.turno_horas if i + n <= a.hasta]

    def ausente(self, persona: str, d: int, turno: Turno) -> bool:
        """Si el turno pisa una ausencia de la persona ese día."""
        for a in self.empresa.ausencias:
            if a.persona == persona and a.fecha == self.fechas[d]:
                if a.desde is None or (turno[0] < a.hasta and a.desde < turno[1]):
                    return True
        return False

    # --- Reglas ---

    def regla(self, tipo: TipoRegla) -> Regla | None:
        return next((r for r in self.reglas if r.tipo == tipo), None)

    def prorrata(self, valor: float, periodo: str | None) -> int:
        """Pasa un límite por mes o año al periodo del cuadrante, redondeando hacia arriba.

        Hacia arriba también en los máximos: un máximo anual no obliga a repartirse por
        igual cada mes, y redondear hacia abajo prohibiría lo que el convenio permite.
        """
        dias = {"mes": 365 / 12, "año": 365}.get(periodo or "", self.n_dias)
        return math.ceil(round(valor * self.n_dias / dias, 6))

    def horas_completa(self) -> int:
        """Horas semanales de una jornada completa bajo este convenio.

        La jornada anual se reparte entre las semanas de trabajo efectivo del año (sin
        vacaciones ni festivos), no entre 52: si no, una completa saldría a cuatro días
        por semana. Nunca por encima del promedio semanal. Se redondea a la hora.
        """
        e = self.empresa
        semanas_efectivas = (365 - e.vacaciones_dias_naturales - e.festivos_anuales) / 7
        semanal = []
        if r := self.regla(TipoRegla.JORNADA_ANUAL_MAX):
            semanal.append(r.valor / semanas_efectivas)
        if r := self.regla(TipoRegla.HORAS_SEMANA_PROMEDIO_MAX):
            semanal.append(r.valor)
        return math.floor(min(semanal))

    def horas_contrato(self, p: Persona) -> int:
        """Horas ordinarias por semana que hay que cumplir."""
        return self.horas_completa() if p.horas_semana == "completa" else p.horas_semana

    def objetivo_periodo(self, p: Persona) -> int:
        """Horas que debería hacer en el periodo para ir cerrando el año en su jornada."""
        return self.horas_contrato(p) * len(self.semanas()) - p.saldo_horas

    def bandas(self) -> list[tuple[float, float]]:
        """Bandas horarias de turno continuo (mañana, tarde, noche) que fija el convenio."""
        out = []
        for r in self.reglas:
            if r.tipo == TipoRegla.TURNO_BANDA and r.turno != "partido":
                ini, fin = hora(r.desde), hora(r.hasta)
                out.append((ini, fin + 24 if fin <= ini else fin))
        return out

    def en_banda(self, t: Turno) -> bool:
        """Sin bandas en el convenio, cualquier turno vale; con bandas, tiene que caber en una."""
        bandas = self.bandas()
        if not bandas:
            return True
        for ini, fin in bandas:
            i = t[0] + 24 if fin > 24 and t[0] < ini else t[0]
            if ini <= i and i + horas(t) <= fin:
                return True
        return False

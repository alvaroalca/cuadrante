"""Comprueba un cuadrante contra las reglas efectivas del convenio, los contratos y la cobertura.

Es independiente del solver a propósito: el solver propone y esto cuenta los
incumplimientos, así que un fallo al traducir una regla a restricción sale aquí. Es
también lo que valida las ediciones a mano: cada incumplimiento lleva su regla, con la
cita y si es pactable.

Un cuadrante es {persona: [turno (inicio, fin) o None por día]}.
"""

from dataclasses import dataclass

from motor.empresa import Contexto, Persona, Turno, horas
from motor.reglas import Regla, TipoRegla

Cuadrante = dict[str, list[Turno | None]]
R = TipoRegla


@dataclass
class Incumplimiento:
    tipo: str  # tipo de regla, "contrato" o "cobertura"
    mensaje: str
    persona: str | None = None
    dias: tuple[int, ...] = ()
    regla: Regla | None = None


def descanso_alrededor(fila: list[Turno | None], d: int) -> float:
    """Horas seguidas de descanso que da librar el día d (0 si se trabaja).

    Fuera del periodo se supone libre: el cuadrante no sabe qué pasó antes ni después.
    """
    if fila[d] is not None:
        return 0.0
    antes = fila[d - 1] if d > 0 else None
    despues = fila[d + 1] if d + 1 < len(fila) else None
    return (24 - antes[1] if antes else 24) + 24 + (despues[0] if despues else 24)


def bolsa_complementarias(ctx: Contexto, p: Persona) -> tuple[int, int]:
    """Horas complementarias (pactadas, voluntarias) que puede hacer en el periodo.

    ET 12.5: solo a tiempo parcial y con contrato de 10 h semanales o más; las pactadas
    piden pacto escrito y las voluntarias, contrato indefinido. El máximo de cada una es
    un % de las horas ordinarias del contrato, el del convenio o el del Estatuto.
    """
    contrato = ctx.horas_contrato(p)
    if not p.parcial or contrato < 10:
        return 0, 0
    semanas = ctx.n_dias / 7
    pactadas = voluntarias = 0
    if p.pacto_complementarias_pct and (r := ctx.regla(R.COMPLEMENTARIAS_PACTADAS_MAX_PCT)):
        pactadas = int(contrato * semanas * min(p.pacto_complementarias_pct, r.valor) / 100)
    if p.indefinido and (r := ctx.regla(R.COMPLEMENTARIAS_VOLUNTARIAS_MAX_PCT)):
        voluntarias = int(contrato * semanas * r.valor / 100)
    return pactadas, voluntarias


def comprobar(ctx: Contexto, cuadrante: Cuadrante, pagadas: dict[str, int] | None = None) -> list[Incumplimiento]:
    """Las ausencias de la ficha no tocan el cuadrante: el turno sigue y sus horas cuentan
    para el contrato (están justificadas), pero no cubren. `pagadas[persona]`: horas de
    más que se pagan (complementarias o extras) y no cuentan para los márgenes del contrato."""
    pagadas = pagadas or {}
    personas = {p.nombre: p for p in ctx.empresa.plantilla}
    out: list[Incumplimiento] = []
    regla = ctx.regla

    for nombre, fila in cuadrante.items():
        trabaja = [t is not None for t in fila]
        hh = [horas(t) if t else 0 for t in fila]

        if r := regla(R.HORAS_DIA_MAX):
            for d, h in enumerate(hh):
                if h > r.valor:
                    out.append(Incumplimiento(r.tipo, f"{h} h en un día; máximo {r.valor:g}", nombre, (d,), r))

        if r := regla(R.DESCANSO_ENTRE_JORNADAS_MIN):
            for d in range(len(fila) - 1):
                if fila[d] and fila[d + 1]:
                    h = 24 + fila[d + 1][0] - fila[d][1]
                    if h < r.valor:
                        out.append(Incumplimiento(r.tipo, f"{h} h entre jornadas; mínimo {r.valor:g}", nombre, (d, d + 1), r))

        if r := regla(R.DIAS_CONSECUTIVOS_MAX):
            n = int(r.valor)
            for v in ctx.ventanas(n + 1):
                if all(trabaja[d] for d in v):
                    out.append(Incumplimiento(r.tipo, f"más de {n} días seguidos", nombre, tuple(v), r))

        for r in (x for x in ctx.reglas if x.tipo == R.DIAS_LIBRES_MIN_EN_VENTANA):
            for v in ctx.ventanas(r.ventana_dias):
                libres = sum(not trabaja[d] for d in v)
                if libres < r.valor:
                    out.append(Incumplimiento(r.tipo, f"{libres} días libres en {r.ventana_dias}; mínimo {r.valor:g}", nombre, tuple(v), r))

        if r := regla(R.DESCANSO_SEMANAL_MIN):
            minimo_h = r.valor * 24
            if r.periodo == "ventana" and r.ventana_dias:
                n = r.ventana_dias
                bloques = [list(range(i, i + n)) for i in range(0, ctx.n_dias - n + 1, n)]
                hace_falta = n // 7
            else:
                bloques, hace_falta = ctx.semanas(), 1
            for b in bloques:
                if sum(descanso_alrededor(fila, d) >= minimo_h for d in b) < hace_falta:
                    out.append(Incumplimiento(r.tipo, f"sin descanso de {minimo_h:g} h seguidas", nombre, tuple(b), r))

        if r := regla(R.FINES_SEMANA_LIBRES_MIN):
            minimo = ctx.prorrata(r.valor, r.periodo)
            libres = sum(not trabaja[s] and not trabaja[d] for s, d in ctx.fines_de_semana())
            if libres < minimo:
                out.append(Incumplimiento(r.tipo, f"{libres} fines de semana libres; mínimo {minimo} en el periodo", nombre, (), r))

        if r := regla(R.DOMINGOS_LIBRES_MIN):
            domingos = set(ctx.domingos())
            if r.periodo == "ventana" and r.ventana_dias and r.ventana_dias <= ctx.n_dias:
                for v in ctx.ventanas(r.ventana_dias):
                    libres = sum(not trabaja[d] for d in v if d in domingos)
                    if libres < r.valor:
                        out.append(Incumplimiento(r.tipo, f"{libres} domingos libres en {r.ventana_dias} días; mínimo {r.valor:g}", nombre, tuple(v), r))
            else:
                minimo = ctx.prorrata(r.valor, r.periodo)
                libres = sum(not trabaja[d] for d in domingos)
                if libres < minimo:
                    out.append(Incumplimiento(r.tipo, f"{libres} domingos libres; mínimo {minimo} en el periodo", nombre, (), r))

        if r := regla(R.DOMINGOS_FESTIVOS_TRABAJO_MAX):
            maximo = ctx.prorrata(r.valor, r.periodo)
            dias = tuple(d for d in range(ctx.n_dias) if trabaja[d] and ctx.es_domingo_o_festivo(d))
            if len(dias) > maximo:
                out.append(Incumplimiento(r.tipo, f"{len(dias)} domingos o festivos; máximo {maximo} en el periodo", nombre, dias, r))

        if r := regla(R.HORAS_SEMANA_TOPE):
            for s in ctx.semanas():
                h = sum(hh[d] for d in s)
                if h > r.valor:
                    out.append(Incumplimiento(r.tipo, f"{h} h en la semana; máximo {r.valor:g}", nombre, tuple(s), r))

        if ctx.bandas():
            for d, t in enumerate(fila):
                if t and not ctx.en_banda(t):
                    r = next(x for x in ctx.reglas if x.tipo == R.TURNO_BANDA)
                    out.append(Incumplimiento(R.TURNO_BANDA, f"{t[0]}-{t[1]} no cabe en ninguna banda de turno", nombre, (d,), r))

        if nombre in personas:
            out += contrato(ctx, personas[nombre], fila, pagadas.get(nombre, 0))

    for d in range(ctx.n_dias):
        for h in range(24):
            falta = ctx.necesidad(d, h)
            if falta:
                hay = sum(1 for n, fila in cuadrante.items()
                          if fila[d] and fila[d][0] <= h < fila[d][1] and not ctx.ausente(n, d, (h, h + 1)))
                if hay < falta:
                    out.append(Incumplimiento("cobertura", f"{hay} de {falta} de {h} a {h + 1}", None, (d,)))
    return out


def contrato(ctx: Contexto, p: Persona, fila: list[Turno | None], pagadas: int = 0) -> list[Incumplimiento]:
    """El contrato no pasa de la jornada completa, y semanas y periodo quedan dentro de los
    márgenes de la empresa. Lo obligatorio es la jornada anual: la diferencia del periodo
    no es un incumplimiento, va al saldo de la persona."""
    out = []
    contrato_h = ctx.horas_contrato(p)
    jornada = ctx.regla(R.JORNADA_ANUAL_MAX) or ctx.regla(R.HORAS_SEMANA_PROMEDIO_MAX)
    if contrato_h > ctx.horas_completa():
        out.append(Incumplimiento(jornada.tipo, f"contrato de {contrato_h} h por encima de la jornada completa ({ctx.horas_completa()} h)", p.nombre, (), jornada))
    e = ctx.empresa
    total = 0
    for s in ctx.semanas():
        h = sum(horas(fila[d]) for d in s if fila[d])
        total += h
        if not contrato_h - e.margen_semanal_horas <= h <= contrato_h + e.margen_semanal_horas + pagadas:
            out.append(Incumplimiento("contrato", f"{h} h en la semana; contrato {contrato_h} ± {e.margen_semanal_horas} de margen", p.nombre, tuple(s)))
    objetivo = ctx.objetivo_periodo(p)
    if not -e.margen_periodo_horas <= total - objetivo <= e.margen_periodo_horas + pagadas:
        out.append(Incumplimiento("contrato", f"{total} h en el periodo; objetivo {objetivo} ± {e.margen_periodo_horas} de margen", p.nombre, ()))
    return out


# Tipos que el comprobador aplica, y por qué no los demás.
APLICADOS = {
    R.HORAS_DIA_MAX, R.DESCANSO_ENTRE_JORNADAS_MIN, R.DIAS_CONSECUTIVOS_MAX, R.DIAS_LIBRES_MIN_EN_VENTANA,
    R.DESCANSO_SEMANAL_MIN, R.FINES_SEMANA_LIBRES_MIN, R.DOMINGOS_LIBRES_MIN, R.DOMINGOS_FESTIVOS_TRABAJO_MAX,
    R.HORAS_SEMANA_TOPE, R.JORNADA_ANUAL_MAX, R.HORAS_SEMANA_PROMEDIO_MAX, R.TURNO_BANDA,
    R.COMPLEMENTARIAS_PACTADAS_MAX_PCT, R.COMPLEMENTARIAS_VOLUNTARIAS_MAX_PCT,
}


def horas_nocturnas(t: Turno) -> int:
    """Horas del turno entre las 22 y las 6 (ET 36.1)."""
    return sum(max(0, min(t[1], b) - max(t[0], a)) for a, b in [(0, 6), (22, 30), (46, 54)])


def estado(ctx: Contexto, r: Regla) -> str:
    """'aplica' o el motivo por el que esta regla no cuenta en este cuadrante."""
    if r.tipo in APLICADOS:
        return "aplica"
    if r.tipo == R.PAUSA_JORNADA_PARTIDA:
        return "no hay turnos partidos"
    if r.tipo in (R.PREAVISO_CAMBIO_MIN, R.REPLANIFICACION_MAX_PLANTILLA, R.PREAVISO_COMPLEMENTARIAS_MIN):
        return "al replanificar"
    if r.tipo == R.DESCANSO_COMPENSATORIO_FESTIVO:
        return "pendiente de implementar" if ctx.empresa.festivos else "no hay festivos en el periodo"
    if r.tipo == R.HORAS_NOCHE_PROMEDIO_MAX:
        # ET 36.1: es trabajador nocturno quien hace normalmente 3 h o más de noche.
        if all(horas_nocturnas(t) < 3 for t in ctx.catalogo()):
            return "ningún turno tiene 3 h nocturnas"
    return "pendiente de implementar"

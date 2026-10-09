"""Monta el cuadrante del periodo con OR-Tools CP-SAT.

Cada persona hace como mucho un turno continuo al día, sacado del catálogo de la empresa
(bloques de horas enteras dentro de la apertura). Cada regla efectiva del convenio es
una restricción dura. La traducción es propia de este módulo y no reutiliza la del
comprobador: si una de las dos se equivoca, el comprobador lo cuenta como incumplimiento.

`construir` pone las reglas; generar (`resolver`) y replanificar (`replanificar.py`)
añaden encima lo suyo: contrato y reparto, o el mínimo cambio y las horas de más.

Uso: uv run python -m motor.solver BOE-A-2023-13741 [más convenios...]
"""

import sys
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from motor.cumplimiento import Cuadrante, comprobar, estado
from motor.empresa import Contexto, Turno, cargar_convenio, cargar_empresa, horas
from motor.reglas import TipoRegla as R


@dataclass
class Resultado:
    estado: str  # "optimo", "factible", "imposible", "sin tiempo"
    cuadrante: Cuadrante | None
    segundos: float


@dataclass
class Modelo:
    ctx: Contexto
    m: cp_model.CpModel
    C: list[Turno]
    x: dict = field(default_factory=dict)  # (persona, día, índice de turno) -> bool
    trabaja: dict = field(default_factory=dict)

    def xs(self, n: str, d: int):
        return [(k, self.x[n, d, k]) for k in range(len(self.C)) if (n, d, k) in self.x]

    def horas_en(self, n: str, dias):
        return sum(horas(self.C[k]) * v for d in dias for k, v in self.xs(n, d))

    def resolver(self, segundos: float, pista: Cuadrante | None = None) -> tuple[str, cp_model.CpSolver]:
        if pista:
            for (n, d, k), v in self.x.items():
                self.m.add_hint(v, pista.get(n, [None] * self.ctx.n_dias)[d] == self.C[k])
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = segundos
        solver.parameters.num_workers = 8
        st = solver.solve(self.m)
        nombres = {cp_model.OPTIMAL: "optimo", cp_model.FEASIBLE: "factible", cp_model.INFEASIBLE: "imposible"}
        return nombres.get(st, "sin tiempo"), solver

    def cuadrante(self, solver: cp_model.CpSolver) -> Cuadrante:
        return {p.nombre: [next((self.C[k] for k, v in self.xs(p.nombre, d) if solver.value(v)), None)
                           for d in range(self.ctx.n_dias)] for p in self.ctx.empresa.plantilla}


def turnos_validos(ctx: Contexto) -> list[Turno]:
    """Turnos del catálogo que ninguna regla prohíbe de por sí: largo del día y bandas."""
    maximo = r.valor if (r := ctx.regla(R.HORAS_DIA_MAX)) else 24
    return [t for t in ctx.catalogo() if horas(t) <= maximo and ctx.en_banda(t)]


def construir(ctx: Contexto, extra: list[Turno] = (), evitar_ausencias: bool = True) -> Modelo:
    """Variables y reglas del convenio. `extra`: turnos que tienen que poder representarse
    aunque no estén en el catálogo (los de un cuadrante editado a mano)."""
    P = ctx.empresa.plantilla
    D = range(ctx.n_dias)
    C = turnos_validos(ctx)
    C += [t for t in dict.fromkeys(extra) if t not in C]
    mod = Modelo(ctx, cp_model.CpModel(), C)
    m, x, trabaja = mod.m, mod.x, mod.trabaja

    for p in P:
        for d in D:
            for k, t in enumerate(C):
                if not (evitar_ausencias and ctx.ausente(p.nombre, d, t)):
                    x[p.nombre, d, k] = m.new_bool_var("")

    ini, fin = {}, {}
    for p in P:
        n = p.nombre
        for d in D:
            trabaja[n, d] = m.new_bool_var("")
            m.add(sum(v for _, v in mod.xs(n, d)) == trabaja[n, d])  # un turno al día como mucho
            ini[n, d] = sum(C[k][0] * v for k, v in mod.xs(n, d))  # 0 si libra
            fin[n, d] = sum(C[k][1] * v for k, v in mod.xs(n, d))

    for p in P:
        n = p.nombre
        if r := ctx.regla(R.HORAS_DIA_MAX):
            for d in D:
                for k, v in mod.xs(n, d):
                    if horas(C[k]) > r.valor:
                        m.add(v == 0)

        if ctx.bandas():
            for d in D:
                for k, v in mod.xs(n, d):
                    if not ctx.en_banda(C[k]):
                        m.add(v == 0)

        if r := ctx.regla(R.DESCANSO_ENTRE_JORNADAS_MIN):
            for d in range(ctx.n_dias - 1):
                ambos = m.new_bool_var("")
                m.add_bool_and([trabaja[n, d], trabaja[n, d + 1]]).only_enforce_if(ambos)
                m.add_bool_or([trabaja[n, d].Not(), trabaja[n, d + 1].Not(), ambos])
                m.add(24 + ini[n, d + 1] - fin[n, d] >= int(r.valor)).only_enforce_if(ambos)

        if r := ctx.regla(R.DIAS_CONSECUTIVOS_MAX):
            for v in ctx.ventanas(int(r.valor) + 1):
                m.add(sum(trabaja[n, d] for d in v) <= int(r.valor))

        for r in (r for r in ctx.reglas if r.tipo == R.DIAS_LIBRES_MIN_EN_VENTANA):
            for v in ctx.ventanas(r.ventana_dias):
                m.add(sum(trabaja[n, d] for d in v) <= len(v) - int(r.valor))

        if r := ctx.regla(R.DESCANSO_SEMANAL_MIN):
            # ok[d]: librar el día d da `minimo` horas seguidas: lo que queda del día
            # anterior desde que acaba el turno, el día libre y lo que pasa del siguiente
            # hasta que empieza (24 si también libra). Fuera del periodo se supone libre.
            minimo = round(r.valor * 24)
            ok = {}
            for d in D:
                ok[d] = m.new_bool_var("")
                m.add_implication(ok[d], trabaja[n, d].Not())
                antes = 24 - fin[n, d - 1] if d > 0 else 24
                despues = ini[n, d + 1] + 24 * (1 - trabaja[n, d + 1]) if d + 1 < ctx.n_dias else 24
                m.add(antes + 24 + despues >= minimo).only_enforce_if(ok[d])
            if r.periodo == "ventana" and r.ventana_dias:
                largo = r.ventana_dias
                bloques = [range(i, i + largo) for i in range(0, ctx.n_dias - largo + 1, largo)]
                hace_falta = largo // 7
            else:
                bloques, hace_falta = ctx.semanas(), 1
            for b in bloques:
                m.add(sum(ok[d] for d in b) >= hace_falta)

        if r := ctx.regla(R.FINES_SEMANA_LIBRES_MIN):
            fs = []
            for s, d in ctx.fines_de_semana():
                f = m.new_bool_var("")
                m.add_implication(f, trabaja[n, s].Not())
                m.add_implication(f, trabaja[n, d].Not())
                fs.append(f)
            m.add(sum(fs) >= ctx.prorrata(r.valor, r.periodo))

        if r := ctx.regla(R.DOMINGOS_LIBRES_MIN):
            domingos = ctx.domingos()
            if r.periodo == "ventana" and r.ventana_dias and r.ventana_dias <= ctx.n_dias:
                for v in ctx.ventanas(r.ventana_dias):
                    dom = [d for d in v if d in domingos]
                    m.add(sum(trabaja[n, d] for d in dom) <= len(dom) - int(r.valor))
            else:
                m.add(sum(trabaja[n, d] for d in domingos) <= len(domingos) - ctx.prorrata(r.valor, r.periodo))

        if r := ctx.regla(R.DOMINGOS_FESTIVOS_TRABAJO_MAX):
            m.add(sum(trabaja[n, d] for d in D if ctx.es_domingo_o_festivo(d)) <= ctx.prorrata(r.valor, r.periodo))

        if r := ctx.regla(R.HORAS_SEMANA_TOPE):
            for s in ctx.semanas():
                m.add(mod.horas_en(n, s) <= int(r.valor))
    return mod


def cobertura(mod: Modelo, blanda: bool = False) -> list:
    """Cada hora con la gente que pide la ficha. Las horas en que alguien está ausente no
    cuentan aunque tenga turno. Blanda: devuelve lo que falta en cada hora para penalizarlo."""
    ctx, m, C = mod.ctx, mod.m, mod.C
    faltas = []
    for d in range(ctx.n_dias):
        for h in range(24):
            if necesidad := ctx.necesidad(d, h):
                hay = sum(v for p in ctx.empresa.plantilla for k, v in mod.xs(p.nombre, d)
                          if C[k][0] <= h < C[k][1] and not ctx.ausente(p.nombre, d, (h, h + 1)))
                if blanda:
                    falta = m.new_int_var(0, necesidad, "")
                    m.add(hay + falta >= necesidad)
                    faltas.append(((d, h), falta))
                else:
                    m.add(hay >= necesidad)
    return faltas


def resolver(ctx: Contexto, segundos: float = 60, pista: Cuadrante | None = None) -> Resultado:
    """Genera el cuadrante del periodo. `pista`: un cuadrante de partida que el solver repara."""
    e, P, D = ctx.empresa, ctx.empresa.plantilla, range(ctx.n_dias)
    mod = construir(ctx)
    m, trabaja = mod.m, mod.trabaja
    cobertura(mod)

    # Lo obligatorio es la jornada anual: el periodo se acerca al objetivo (contrato
    # menos saldo) dentro del margen de la empresa, y cada semana se desvía del contrato
    # como mucho su margen.
    desvios = []
    for p in P:
        n, contrato_h, objetivo = p.nombre, ctx.horas_contrato(p), ctx.objetivo_periodo(p)
        total = mod.horas_en(n, D)
        m.add(total >= objetivo - e.margen_periodo_horas)
        m.add(total <= objetivo + e.margen_periodo_horas)
        desvio = m.new_int_var(0, e.margen_periodo_horas, "")
        m.add_abs_equality(desvio, total - objetivo)
        desvios.append(desvio)
        for s in ctx.semanas():
            m.add(mod.horas_en(n, s) >= contrato_h - e.margen_semanal_horas)
            m.add(mod.horas_en(n, s) <= contrato_h + e.margen_semanal_horas)

    # Objetivo: cada uno cerca de sus horas, pocos días de trabajo por persona (turnos
    # largos antes que muchos cortos) y fines de semana repartidos con justicia entre
    # quienes tienen el mismo contrato.
    finde = [d for d in D if ctx.fechas[d].weekday() >= 5]
    desigualdad = []
    for grupo in {ctx.horas_contrato(p) for p in P}:
        miembros = [p.nombre for p in P if ctx.horas_contrato(p) == grupo]
        alto, bajo = m.new_int_var(0, len(finde), ""), m.new_int_var(0, len(finde), "")
        for n in miembros:
            m.add(sum(trabaja[n, d] for d in finde) <= alto)
            m.add(sum(trabaja[n, d] for d in finde) >= bajo)
        desigualdad.append(alto - bajo)
    m.minimize(4 * sum(desvios) + sum(trabaja.values()) + 5 * sum(desigualdad))

    st, solver = mod.resolver(segundos, pista)
    if st not in ("optimo", "factible"):
        return Resultado(st, None, solver.wall_time)
    return Resultado(st, mod.cuadrante(solver), solver.wall_time)


def imprimir(ctx: Contexto, res: Resultado, semanas: int = 1) -> None:
    print(f"\n== {ctx.convenio.nombre} ({ctx.convenio.boe}): {res.estado} en {res.segundos:.1f} s · completa = {ctx.horas_completa()} h")
    for r in ctx.reglas:
        valor = f"{r.valor:g}" if r.valor is not None else f"{r.turno} {r.desde}-{r.hasta}"
        print(f"   {estado(ctx, r):32} {r.tipo.value:36} {valor:>14}  {r.cita.articulo}")
    if not res.cuadrante:
        return
    for s in ctx.semanas()[:semanas]:
        print(f"\n   {'':8}" + "".join(f"{'LMXJVSD'[ctx.fechas[d].weekday()]}{ctx.fechas[d].day:<6}" for d in s) + " horas")
        for p, fila in res.cuadrante.items():
            celdas = "".join(f"{t[0]:02}-{t[1]:<4}" if t else "  ·    " for t in (fila[d] for d in s))
            print(f"   {p:8}{celdas}{sum(horas(fila[d]) for d in s if fila[d]):>4}")
    print("\n   Saldo al cerrar el periodo (+ de más, - debe):")
    for p in ctx.empresa.plantilla:
        hechas = sum(horas(t) for t in res.cuadrante[p.nombre] if t)
        print(f"     {p.nombre:8} {hechas:>4} h de {ctx.objetivo_periodo(p):>4}  saldo {p.saldo_horas + hechas - ctx.horas_contrato(p) * len(ctx.semanas()):+}")
    fallos = comprobar(ctx, res.cuadrante)
    print(f"\n   Incumplimientos según el comprobador: {len(fallos)}")
    for f in fallos[:10]:
        print(f"     - {f.persona or ''} {f.tipo}: {f.mensaje}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    empresa = cargar_empresa()
    for boe in sys.argv[1:]:
        ctx = Contexto.crear(empresa, cargar_convenio(boe))
        imprimir(ctx, resolver(ctx))

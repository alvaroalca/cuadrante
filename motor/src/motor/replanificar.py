"""Recoloca un cuadrante cuando falta alguien.

Todo queda fijo menos los días de la ausencia, y esos días solo se añaden horas: alargar
el turno de alguien o darle uno si libraba. Nadie cambia de turno. Cada hora añadida es
de una de cuatro clases, de la más barata a la más cara:

- redistribución: va al saldo y se recupera más adelante; es distribución irregular y
  pide el preaviso del ET 34.2 (o el del convenio para cambiar horarios, si es mayor).
- complementarias voluntarias (ET 12.5.g): parcial, indefinido y de 10 h o más.
- complementarias pactadas (ET 12.5.a-d): parcial con pacto y de 10 h o más, con preaviso.
- extraordinarias: solo jornada completa (ET 12.4.c) y siempre voluntarias (ET 35.4).

Uso: uv run python -m motor.replanificar BOE-A-2023-13741 [...]
"""

import json
import math
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from motor.cumplimiento import Cuadrante, Incumplimiento, bolsa_complementarias, comprobar
from motor.empresa import RAIZ, Acuerdo, Ausencia, Contexto, Persona, cargar_convenio, cargar_empresa, horas
from motor.reglas import ESTATUTO, Cita, Regla, TipoRegla as R
from motor.solver import construir, cobertura, resolver

CLASES = ("redistribucion", "voluntarias", "pactadas", "extras")
COSTE = {"redistribucion": 1, "voluntarias": 2, "pactadas": 3, "extras": 10}
EXTRAS = Regla(tipo=R.OTRA, descripcion="Horas extraordinarias", origen="estatuto", cita=Cita(
    articulo="ET 35.4", texto="La prestación de trabajo en horas extraordinarias será voluntaria"))
SIN_EXTRAS = Regla(tipo=R.OTRA, descripcion="Tiempo parcial sin extraordinarias", origen="estatuto", cita=Cita(
    articulo="ET 12.4.c", texto="Los trabajadores a tiempo parcial no podrán realizar horas extraordinarias"))


@dataclass
class Cambio:
    persona: str
    dia: int
    antes: tuple[int, int] | None
    despues: tuple[int, int]
    horas: dict[str, int]  # clase -> horas añadidas en esta celda, en el orden en que se pintan


@dataclass
class Opcion:
    clase: str
    puede: bool
    motivo: str
    regla: Regla | None = None


@dataclass
class Replan:
    estado: str
    cuadrante: Cuadrante | None
    cambios: list[Cambio]
    sin_cubrir: list[tuple[int, int, int]]  # día, hora, personas que faltan
    opciones: dict[str, list[Opcion]]  # por persona: qué clases puede hacer y por qué
    incumplimientos: list[Incumplimiento]


def plazo(r: Regla) -> str:
    return f"{r.valor:g} {'días' if r.unidad == 'dias' else r.unidad}"


def en_horas(r: Regla) -> float:
    return r.valor * 24 if r.unidad == "dias" else r.valor


def preaviso(ctx: Contexto, clase: str, imprevista: bool) -> Regla | None:
    """Regla de preaviso que manda para una clase de hora añadida."""
    if clase == "pactadas":
        if imprevista:
            activas = set(ctx.empresa.condiciones_imprevistas.get(ctx.convenio.boe, []))
            for r in ctx.convenio.reglas:
                if r.tipo == R.PREAVISO_COMPLEMENTARIAS_MIN and r.condicion in activas:
                    return r
        return ctx.regla(R.PREAVISO_COMPLEMENTARIAS_MIN)
    if clase == "redistribucion":
        et = next(r for r in ESTATUTO if r.tipo == R.PREAVISO_CAMBIO_MIN)  # ET 34.2: 5 días
        conv = ctx.regla(R.PREAVISO_CAMBIO_MIN)
        return conv if conv and en_horas(conv) > en_horas(et) else et
    return None


def opciones(ctx: Contexto, p: Persona, antelacion_h: float, imprevista: bool) -> list[Opcion]:
    """Qué clases de hora puede hacer una persona y por qué no las demás."""
    contrato = ctx.horas_contrato(p)
    pactadas, voluntarias = bolsa_complementarias(ctx, p)
    out = []
    r = preaviso(ctx, "redistribucion", imprevista)
    falta = antelacion_h < en_horas(r)
    out.append(Opcion("redistribucion", not falta, f"pide {plazo(r)} de preaviso" if falta else "recupera las horas más adelante", r))
    if not p.parcial:
        out.append(Opcion("voluntarias", False, "las complementarias son de tiempo parcial"))
        out.append(Opcion("pactadas", False, "las complementarias son de tiempo parcial"))
        out.append(Opcion("extras", True, "voluntarias para la persona", EXTRAS))
        return out
    if contrato < 10:
        motivo = f"contrato de {contrato} h: hacen falta 10 h semanales para complementarias"
        out += [Opcion("voluntarias", False, motivo), Opcion("pactadas", False, motivo)]
    else:
        rv = ctx.regla(R.COMPLEMENTARIAS_VOLUNTARIAS_MAX_PCT)
        out.append(Opcion("voluntarias", p.indefinido, f"hasta {voluntarias} h en el periodo" if p.indefinido else "solo con contrato indefinido", rv))
        rp = preaviso(ctx, "pactadas", imprevista)
        if not p.pacto_complementarias_pct:
            out.append(Opcion("pactadas", False, "no tiene pacto de complementarias"))
        elif antelacion_h < en_horas(rp):
            out.append(Opcion("pactadas", False, f"pide {plazo(rp)} de preaviso", rp))
        else:
            out.append(Opcion("pactadas", True, f"hasta {pactadas} h en el periodo", rp))
    out.append(Opcion("extras", False, "a tiempo parcial no hay extraordinarias", SIN_EXTRAS))
    return out


def replanificar(ctx: Contexto, base: Cuadrante, ausencias: list[Ausencia], segundos: float = 30,
                 acuerdos: list[Acuerdo] = ()) -> Replan:
    empresa = ctx.empresa.model_copy(update={"ausencias": ctx.empresa.ausencias + ausencias})
    ctx = Contexto(empresa, ctx.convenio, ctx.reglas)
    P, D = empresa.plantilla, range(ctx.n_dias)
    dias = sorted({ctx.fechas.index(a.fecha) for a in ausencias})
    # Antelación: la peor de las ausencias de cada día, desde que se avisa.
    antelacion = {}
    for a in ausencias:
        aviso = a.aviso or a.fecha - timedelta(days=1)
        h = (a.fecha - aviso).days * 24 + (a.desde or 0)
        d = ctx.fechas.index(a.fecha)
        antelacion[d] = min(antelacion.get(d, h), h)
    imprevista = any(a.imprevista for a in ausencias)
    ausentes = {(a.persona, ctx.fechas.index(a.fecha)) for a in ausencias}

    mod = construir(ctx, extra=[t for fila in base.values() for t in fila if t], evitar_ausencias=False,
                    exentas={(a.persona, a.tipo) for a in acuerdos})
    m, C = mod.m, mod.C

    # Mínimo cambio: todo fijo salvo los días de la ausencia, y esos días solo crecer.
    for p in P:
        n = p.nombre
        for d in D:
            t0 = base[n][d]
            for k, v in mod.xs(n, d):
                fijo = d not in dias or (n, d) in ausentes
                if fijo:
                    m.add(v == int(C[k] == t0))
                elif t0 and not (C[k][0] <= t0[0] and C[k][1] >= t0[1]):
                    m.add(v == 0)
            if t0 and d in dias and (n, d) not in ausentes:
                m.add(mod.trabaja[n, d] == 1)

    faltas = cobertura(mod, blanda=True)

    ops = {p.nombre: {o.clase: o for o in opciones(ctx, p, min(antelacion.values()), imprevista)} for p in P}
    horas_clase, tocado, impuesto = {}, [], []
    for p in P:
        n = p.nombre
        pactadas, voluntarias = bolsa_complementarias(ctx, p)
        tope = {"redistribucion": empresa.margen_periodo_horas, "voluntarias": voluntarias,
                "pactadas": pactadas, "extras": 24 * len(dias)}
        anadidas = mod.horas_en(n, dias) - sum(horas(base[n][d]) for d in dias if base[n][d])
        for c in CLASES:
            horas_clase[n, c] = m.new_int_var(0, tope[c] if ops[n][c].puede else 0, "")
        m.add(sum(horas_clase[n, c] for c in CLASES) == anadidas)
        t = m.new_bool_var("")
        m.add(anadidas == 0).only_enforce_if(t.Not())
        tocado.append(t)
        i = m.new_bool_var("")  # cambio impuesto (no voluntario): redistribución o pactadas
        m.add(horas_clase[n, "redistribucion"] + horas_clase[n, "pactadas"] == 0).only_enforce_if(i.Not())
        impuesto.append(i)
    if r := ctx.regla(R.REPLANIFICACION_MAX_PLANTILLA):
        m.add(sum(impuesto) <= math.floor(r.valor * len(P) / 100))

    m.minimize(1000 * sum(f for _, f in faltas) + 3 * sum(tocado)
               + sum(COSTE[c] * v for (_, c), v in horas_clase.items()))
    st, solver = mod.resolver(segundos, pista=base)
    if st not in ("optimo", "factible"):
        return Replan(st, None, [], [], {n: list(o.values()) for n, o in ops.items()}, [])

    nuevo = mod.cuadrante(solver)
    cambios = []
    for p in P:
        # Las horas de cada clase son del periodo; se reparten entre las celdas que crecen, de la más barata a la más cara.
        bolsa = [[c, solver.value(horas_clase[p.nombre, c])] for c in CLASES]
        for d in dias:
            if nuevo[p.nombre][d] != base[p.nombre][d]:
                falta, celda = horas(nuevo[p.nombre][d]) - horas(base[p.nombre][d] or (0, 0)), {}
                for b in bolsa:
                    h = min(falta, b[1])
                    if h:
                        celda[b[0]] = h; b[1] -= h; falta -= h
                cambios.append(Cambio(p.nombre, d, base[p.nombre][d], nuevo[p.nombre][d], celda))
    sin_cubrir = [(d, h, solver.value(f)) for (d, h), f in faltas if solver.value(f)]
    pagadas = {p.nombre: sum(solver.value(horas_clase[p.nombre, c]) for c in ("voluntarias", "pactadas", "extras")) for p in P}
    return Replan(st, nuevo, cambios, sin_cubrir, {n: list(o.values()) for n, o in ops.items()}, comprobar(ctx, nuevo, pagadas))


# --- Cuadrantes de partida guardados, para no regenerarlos en cada prueba ---

def cuadrante_base(ctx: Contexto) -> Cuadrante:
    ruta = RAIZ / "demo" / "cuadrantes" / f"{ctx.convenio.boe}.json"
    if ruta.exists():
        return {n: [tuple(t) if t else None for t in fila] for n, fila in json.loads(ruta.read_text(encoding="utf-8")).items()}
    res = resolver(ctx)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(res.cuadrante, ensure_ascii=False), encoding="utf-8")
    return res.cuadrante


def nombre_dia(ctx: Contexto, d: int) -> str:
    return f"{'LMXJVSD'[ctx.fechas[d].weekday()]} {ctx.fechas[d].day}"


def imprimir(ctx: Contexto, rp: Replan) -> None:
    print(f"\n== {ctx.convenio.nombre}: {rp.estado}")
    for c in rp.cambios:
        antes = f"{c.antes[0]}-{c.antes[1]}" if c.antes else "libre"
        clases = ", ".join(f"{h} h {cl}" for cl, h in c.horas.items())
        print(f"   {c.persona:7} {nombre_dia(ctx, c.dia)}: {antes:>6} -> {c.despues[0]}-{c.despues[1]}   ({clases})")
    if rp.sin_cubrir:
        print("   Sin cubrir:", ", ".join(f"{nombre_dia(ctx, d)} {h}-{h + 1} (faltan {n})" for d, h, n in rp.sin_cubrir))
    print(f"   Incumplimientos según el comprobador: {len(rp.incumplimientos)}")
    for i in rp.incumplimientos[:5]:
        print(f"     - {i.persona} {i.tipo}: {i.mensaje}")
    print("   Quién puede qué:")
    for n, ops in rp.opciones.items():
        print(f"     {n:7} " + " | ".join(f"{o.clase}: {'sí' if o.puede else 'no'} ({o.motivo})" for o in ops))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    empresa = cargar_empresa()
    # Escenario de prueba: la primera persona a jornada completa que trabaja el martes 10
    # se pone de baja ese día, y avisa el lunes 9.
    dia = date(2026, 11, 10)
    for boe in sys.argv[1:]:
        ctx = Contexto.crear(empresa, cargar_convenio(boe))
        base = cuadrante_base(ctx)
        d = ctx.fechas.index(dia)
        quien = next(p.nombre for p in empresa.plantilla if not p.parcial and base[p.nombre][d])
        print(f"\n{quien} ({base[quien][d][0]}-{base[quien][d][1]}) de baja el {dia:%d/%m}, aviso el día antes")
        ausencias = [Ausencia(persona=quien, fecha=dia, motivo="baja", aviso=dia - timedelta(days=1))]
        imprimir(ctx, replanificar(ctx, base, ausencias))

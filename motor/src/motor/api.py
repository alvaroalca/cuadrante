"""API local para la web. Solo para la demo: sin autenticación y en localhost.

Arrancar: cd motor && uv run uvicorn motor.api:app --reload
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from motor.cumplimiento import Incumplimiento, comprobar, editar, estado
from motor.empresa import RAIZ, Acuerdo, Ausencia, Contexto, cargar_convenio, cargar_empresa
from motor.reglas import Regla
from motor.replanificar import cuadrante_base, replanificar

app = FastAPI(title="Cuadrante")


def contexto(boe: str) -> Contexto:
    if not (RAIZ / "reglas" / f"{boe}.json").exists():
        raise HTTPException(404, f"No hay reglas para {boe}")
    return Contexto.crear(cargar_empresa(), cargar_convenio(boe))


def regla_json(ctx: Contexto, r: Regla) -> dict:
    return {**r.model_dump(mode="json", exclude_none=True), "estado": estado(ctx, r)}


def incumplimiento_json(i: Incumplimiento, acuerdos: list[Acuerdo] = ()) -> dict:
    return {
        "tipo": str(i.tipo),
        "mensaje": i.mensaje,
        "persona": i.persona,
        "dias": list(i.dias),
        "regla": i.regla.model_dump(mode="json", exclude_none=True) if i.regla else None,
        "nivel": i.nivel,
        "pactado": i.pactado(acuerdos),
    }


def cuadrante_json(c) -> dict:
    return {n: [list(t) if t else None for t in fila] for n, fila in c.items()}


def cuadrante_de(datos: dict) -> dict:
    return {n: [tuple(t) if t else None for t in fila] for n, fila in datos.items()}


@app.get("/api/convenios")
def convenios():
    out = []
    for ruta in sorted((RAIZ / "reglas").glob("*.json")):
        c = cargar_convenio(ruta.stem)
        out.append({"boe": c.boe, "nombre": c.nombre, "reglas": len(c.reglas)})
    return out


@app.get("/api/convenios/{boe}")
def convenio(boe: str):
    ctx = contexto(boe)
    return {
        "boe": boe,
        "nombre": ctx.convenio.nombre,
        "completa": ctx.horas_completa(),
        "efectivas": [regla_json(ctx, r) for r in ctx.reglas],
        # Lo que el convenio dice y no se aplica (condiciones que la empresa no cumple, 'otra'):
        "resto": [r.model_dump(mode="json", exclude_none=True) for r in ctx.convenio.reglas if r not in ctx.reglas],
    }


@app.get("/api/cuadrante/{boe}")
def cuadrante(boe: str):
    ctx = contexto(boe)
    base = cuadrante_base(ctx)
    e = ctx.empresa
    return {
        "empresa": e.nombre,
        "fechas": [f.isoformat() for f in ctx.fechas],
        "semanas": ctx.semanas(),
        "apertura": e.apertura.model_dump(),
        "necesidad": [[ctx.necesidad(d, h) for h in range(24)] for d in range(ctx.n_dias)],
        "plantilla": [
            {**p.model_dump(), "contrato": ctx.horas_contrato(p), "objetivo": ctx.objetivo_periodo(p)}
            for p in e.plantilla
        ],
        "cuadrante": cuadrante_json(base),
        "incumplimientos": [incumplimiento_json(i) for i in comprobar(ctx, base)],
    }


def con_ausencias(ctx: Contexto, ausencias: list[Ausencia]) -> Contexto:
    if not ausencias:
        return ctx
    e = ctx.empresa.model_copy(update={"ausencias": ctx.empresa.ausencias + ausencias})
    return Contexto(e, ctx.convenio, ctx.reglas)


class Comprobar(BaseModel):
    cuadrante: dict[str, list[list[int] | None]]
    ausencias: list[Ausencia] = []
    acuerdos: list[Acuerdo] = []


@app.post("/api/comprobar/{boe}")
def comprobar_cuadrante(boe: str, cuerpo: Comprobar):
    ctx = con_ausencias(contexto(boe), cuerpo.ausencias)
    return [incumplimiento_json(i, cuerpo.acuerdos) for i in comprobar(ctx, cuadrante_de(cuerpo.cuadrante))]


class Editar(Comprobar):
    persona: str
    dia: int
    turno: tuple[int, int] | None  # None: libra; fin > 24 si cruza la medianoche


@app.post("/api/editar/{boe}")
def editar_celda(boe: str, cuerpo: Editar):
    """Valida una edición a mano. `nivel` es lo peor que trae: ok, aviso, acuerdo o bloqueo."""
    ctx = con_ausencias(contexto(boe), cuerpo.ausencias)
    c = cuadrante_de(cuerpo.cuadrante)
    if cuerpo.persona not in c or not 0 <= cuerpo.dia < ctx.n_dias:
        raise HTTPException(422, "Persona o día fuera del cuadrante")
    if cuerpo.turno and not (0 <= cuerpo.turno[0] < 24 and cuerpo.turno[0] < cuerpo.turno[1] <= cuerpo.turno[0] + 24):
        raise HTTPException(422, "Turno no válido")
    nuevo, nuevos, todos = editar(ctx, c, cuerpo.persona, cuerpo.dia, cuerpo.turno, cuerpo.acuerdos)
    niveles = {i.nivel for i in nuevos}
    return {
        "nivel": next((n for n in ("bloqueo", "acuerdo", "aviso") if n in niveles), "ok"),
        "nuevos": [incumplimiento_json(i) for i in nuevos],
        "cuadrante": cuadrante_json(nuevo),
        "incumplimientos": [incumplimiento_json(i, cuerpo.acuerdos) for i in todos],
    }


class Replanificar(BaseModel):
    cuadrante: dict[str, list[list[int] | None]]
    ausencias: list[Ausencia]
    acuerdos: list[Acuerdo] = []


@app.post("/api/replanificar/{boe}")
def replanificar_cuadrante(boe: str, cuerpo: Replanificar):
    ctx = contexto(boe)
    for a in cuerpo.ausencias:
        if a.fecha not in ctx.fechas:
            raise HTTPException(422, f"{a.fecha} está fuera del periodo")
    rp = replanificar(ctx, cuadrante_de(cuerpo.cuadrante), cuerpo.ausencias, acuerdos=cuerpo.acuerdos)
    return {
        "estado": rp.estado,
        "cuadrante": cuadrante_json(rp.cuadrante) if rp.cuadrante else None,
        "cambios": [
            {"persona": c.persona, "dia": c.dia, "antes": list(c.antes) if c.antes else None,
             "despues": list(c.despues), "horas": c.horas}
            for c in rp.cambios
        ],
        "sin_cubrir": [{"dia": d, "hora": h, "faltan": n} for d, h, n in rp.sin_cubrir],
        "opciones": {
            n: [{"clase": o.clase, "puede": o.puede, "motivo": o.motivo,
                 "regla": o.regla.model_dump(mode="json", exclude_none=True) if o.regla else None} for o in ops]
            for n, ops in rp.opciones.items()
        },
        "incumplimientos": [incumplimiento_json(i, cuerpo.acuerdos) for i in rp.incumplimientos],
    }

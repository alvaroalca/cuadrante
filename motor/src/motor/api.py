"""API local para la web. Solo para la demo: sin autenticación y en localhost.

Arrancar: cd motor && uv run uvicorn motor.api:app --reload
"""

import json
from datetime import date

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from motor.acciones import HISTORIAL, Estado, ejecutar, pagadas, tuplas
from motor.acciones import contexto as contexto_estado
from motor.agente import conversar
from motor.cumplimiento import Incumplimiento, comprobar, estado
from motor.empresa import RAIZ, Acuerdo, Contexto, cargar_convenio, cargar_empresa
from motor.reglas import Regla
from motor.replanificar import cuadrante_base

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


# --- Acciones y agente: el estado entero viaja en cada petición, con su historial para deshacer ---

def incumplimientos_de(e: Estado) -> list[dict]:
    ctx = contexto_estado(e.boe, e.ausencias)
    return [incumplimiento_json(i, e.acuerdos) for i in comprobar(ctx, tuplas(e.cuadrante), pagadas(e))]


class Accion(BaseModel):
    estado: Estado
    historial: list[Estado] = []
    nombre: str
    args: dict = {}
    hoy: date


@app.post("/api/accion")
def accion(cuerpo: Accion):
    """Lo que se hace a mano en la hoja, por la misma vía que el agente."""
    e, historial = cuerpo.estado, cuerpo.historial
    if cuerpo.nombre == "deshacer":
        if not historial:
            raise HTTPException(409, "No hay nada que deshacer")
        e, historial = historial[-1], historial[:-1]
        return {"estado": e, "historial": historial, "texto": "Deshecho.", "resaltar": [], "incumplimientos": incumplimientos_de(e)}
    try:
        r = ejecutar(cuerpo.nombre, e, cuerpo.hoy, cuerpo.args)
    except httpx.HTTPError as x:
        raise HTTPException(503, f"El motor no responde: {x}")
    if r.cambio:
        historial = [*historial, e][-HISTORIAL:]
    return {"estado": r.estado, "historial": historial, "texto": r.texto, "nivel": r.nivel, "ir_a": r.ir_a,
            "resaltar": r.resaltar, "incidencias": [incumplimiento_json(i) for i in r.incidencias],
            "incumplimientos": incumplimientos_de(r.estado)}


class Mensaje(BaseModel):
    estado: Estado
    historial: list[Estado] = []
    mensajes: list[dict] = []
    texto: str
    hoy: date


@app.post("/api/agente")
def agente(cuerpo: Mensaje):
    """Una instrucción al agente. Responde NDJSON: un evento por acción y uno final con el estado."""
    def eventos():
        try:
            for ev in conversar(cuerpo.estado, cuerpo.historial, cuerpo.mensajes, cuerpo.texto, cuerpo.hoy):
                if ev["tipo"] == "fin":
                    ev["incumplimientos"] = incumplimientos_de(Estado.model_validate(ev["estado"]))
                yield json.dumps(ev, ensure_ascii=False, default=str) + "\n"
        except httpx.HTTPError as x:
            yield json.dumps({"tipo": "error", "texto": f"El modelo no responde (¿está Ollama arrancado?): {x}"}, ensure_ascii=False) + "\n"
    return StreamingResponse(eventos(), media_type="application/x-ndjson")

"""Acciones sobre el cuadrante: las mismas para la mano (diálogos, celdas) y para el agente.

Cada acción recibe el estado, lo valida con el comprobador o el solver y devuelve el estado
nuevo con un texto para el agente. El estado viaja entero entre la web y el motor (es una
demo local de una sola persona), con un historial de fotos para deshacer.

Lo que dice el usuario ("el jueves", "de tarde", "marat") lo interpreta el código, no el modelo.
"""

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from motor.cumplimiento import Incumplimiento, comprobar, editar_celdas
from motor.empresa import RAIZ, Acuerdo, Ausencia, Contexto, cargar_convenio, cargar_empresa, horas
from motor.reglas import Regla
from motor.replanificar import cuadrante_base, replanificar

Celda = list[int] | None
HISTORIAL = 30

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

CONVENIOS = {"grandes almacenes": "BOE-A-2023-13740", "contact center": "BOE-A-2023-13741", "dependencia": "BOE-A-2023-13742"}


class Estado(BaseModel):
    boe: str
    cuadrante: dict[str, list[Celda]]
    ausencias: list[Ausencia] = []
    acuerdos: list[Acuerdo] = []
    # Horas que no son normales, por celda "persona|día": {hora: clase}. Las nocturnas no se guardan: salen de la hora.
    clases: dict[str, dict[int, str]] = {}


@dataclass
class Resultado:
    texto: str  # lo que lee el agente
    estado: Estado
    cambio: bool = False  # si hay que guardar foto para deshacer
    resaltar: list[tuple[str, int]] = field(default_factory=list)  # celdas que cambiaron
    ir_a: str | None = None  # fecha que enseñar
    nivel: str | None = None  # en ediciones: ok, aviso, acuerdo, bloqueo
    incidencias: list[Incumplimiento] = field(default_factory=list)  # las que trae una edición


def estado_inicial(boe: str) -> Estado:
    ctx = contexto(boe)
    return Estado(boe=boe, cuadrante={n: [list(t) if t else None for t in fila] for n, fila in cuadrante_base(ctx).items()})


def contexto(boe: str, ausencias: list[Ausencia] = ()) -> Contexto:
    if not (RAIZ / "reglas" / f"{boe}.json").exists():
        raise ValueError(f"No hay reglas para {boe}")
    ctx = Contexto.crear(cargar_empresa(), cargar_convenio(boe))
    if ausencias:
        e = ctx.empresa.model_copy(update={"ausencias": ctx.empresa.ausencias + list(ausencias)})
        ctx = Contexto(e, ctx.convenio, ctx.reglas)
    return ctx


def pagadas(e: Estado) -> dict[str, int]:
    """Horas complementarias y extraordinarias por persona: se pagan aparte y no cuentan para el contrato."""
    out: dict[str, int] = {}
    for k, horas_ in e.clases.items():
        n = k.split("|")[0]
        out[n] = out.get(n, 0) + sum(1 for c in horas_.values() if c in ("voluntarias", "pactadas", "extras"))
    return out


def tuplas(c: dict[str, list[Celda]]) -> dict:
    return {n: [tuple(t) if t else None for t in fila] for n, fila in c.items()}


def listas(c: dict) -> dict[str, list[Celda]]:
    return {n: [list(t) if t else None for t in fila] for n, fila in c.items()}


# --- Interpretar lo que dice el usuario ---

class Dia(BaseModel):
    relativo: Literal["", "hoy", "mañana", "pasado mañana"] = ""
    dia_semana: Literal["", *DIAS] = ""
    dia_mes: int = 0  # 0: no lo dice
    que_viene: bool = False  # "el lunes que viene", "el próximo martes"


def normal(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower().strip()) if unicodedata.category(c) != "Mn")


def resolver_dia(d: Dia, base: date, hoy: date) -> date | None:
    """Fecha de un día dicho en la frase. `base`: desde dónde se busca (hoy, o el inicio para el fin)."""
    if d.relativo:
        return hoy + timedelta(days=["hoy", "mañana", "pasado mañana"].index(d.relativo))
    if d.dia_mes:
        f = base.replace(day=1)
        for _ in range(2):  # este mes o el siguiente
            try:
                c = f.replace(day=d.dia_mes)
            except ValueError:
                return None
            if c >= hoy:
                return c
            f = (f + timedelta(days=32)).replace(day=1)
        return None
    if d.dia_semana:
        dias = (DIAS.index(d.dia_semana) - base.weekday()) % 7
        if d.que_viene:  # el de la semana siguiente a la de hoy
            lunes = hoy - timedelta(days=hoy.weekday()) + timedelta(days=7)
            return lunes + timedelta(days=DIAS.index(d.dia_semana))
        return base + timedelta(days=dias)
    return None



def persona_de(ctx: Contexto, texto: str | None) -> str | None:
    """Nombre de la plantilla que corresponde, aunque venga sin tildes o con una falta."""
    if not texto:
        return None
    nombres = {normal(p.nombre): p.nombre for p in ctx.empresa.plantilla}
    t = normal(texto)
    if t in nombres:
        return nombres[t]
    cerca = difflib.get_close_matches(t, nombres, n=1, cutoff=0.6)
    return nombres[cerca[0]] if cerca else None


def fecha_de(texto: str | None, hoy: date, base: date | None = None) -> date | None:
    """'hoy', 'mañana', 'el jueves', 'juebes', 'el 12', 'lunes que viene', 'finde', '2026-11-12'."""
    if not texto:
        return None
    t = normal(texto)
    if m := re.fullmatch(r"\s*(\d{4})-(\d{2})-(\d{2})\s*", t):
        return date(int(m[1]), int(m[2]), int(m[3]))
    base = base or hoy
    palabras = re.findall(r"\w+", t)
    d = Dia(que_viene=any(w in ("viene", "proximo", "siguiente") for w in palabras))
    if "pasado" in palabras and ("manana" in palabras or "mnn" in palabras):
        d.relativo = "pasado mañana"
    elif "hoy" in palabras:
        d.relativo = "hoy"
    elif palabras and palabras[0] in ("manana", "mnn", "mñn") and len(palabras) <= 3:
        d.relativo = "mañana"
    elif numeros := [int(w) for w in palabras if w.isdigit()]:
        d.dia_mes = numeros[0]
    elif "finde" in palabras or "fin" in palabras and "semana" in palabras:
        d.dia_semana = "sábado"
    else:
        semana = {normal(x): x for x in DIAS}
        for w in palabras:
            if c := difflib.get_close_matches(w, semana, n=1, cutoff=0.7):
                d.dia_semana = semana[c[0]]
                break
        else:
            return None
    return resolver_dia(d, base, hoy)


def turno_de(ctx: Contexto, texto: str) -> tuple[int, int] | None | str:
    """'mañana', 'tarde', 'noche', 'libre' o '9-17'. Devuelve un texto de error si no se entiende."""
    t = normal(texto)
    a = ctx.empresa.apertura
    medio = (a.desde + a.hasta) // 2
    if any(w in t for w in ("libre", "descans", "nada", "fiesta", "librar")):
        return None
    if m := re.search(r"(\d{1,2})(?::00)?\s*(?:-|–|a|hasta)\s*(?:las\s*)?(\d{1,2})", t):
        i, f = int(m[1]), int(m[2])
        if i > 23 or f > 24 or i == f:
            return f"«{texto}» no es un turno válido."
        return (i, f if f > i else f + 24)
    if "noche" in t or "nocturn" in t:
        return (22, 30)
    if "tarde" in t:
        return (medio, a.hasta)
    if "manana" in t or "mnn" in t:
        return (a.desde, medio)
    return f"No entiendo el turno «{texto}». Usa mañana, tarde, noche, libre o horas como 9-17."


def nombre_dia(f: date) -> str:
    return f"{DIAS[f.weekday()]} {f.day}/{f.month}"


def fmt(t) -> str:
    if not t:
        return "libre"
    return f"{t[0]}-{t[1] if t[1] <= 24 else t[1] - 24}"


def cita(r: Regla | None) -> str:
    if not r:
        return ""
    art = r.cita.articulo if r.origen == "estatuto" else f"art. {r.cita.articulo}"
    return f" ({art}: «{r.cita.texto}»)"


# --- Acciones ---

def ver_cuadrante(e: Estado, hoy: date, persona: str = "", dia: str = "") -> Resultado:
    ctx = contexto(e.boe, e.ausencias)
    quien = persona_de(ctx, persona) if persona else None
    if persona and not quien:
        return Resultado(f"No hay nadie llamado «{persona}» en la plantilla.", e)
    if dia:
        f = fecha_de(dia, hoy)
        if not f or f not in ctx.fechas:
            return Resultado(f"«{dia}» no cae dentro del cuadrante ({nombre_dia(ctx.fechas[0])} al {nombre_dia(ctx.fechas[-1])}).", e)
        dias = [ctx.fechas.index(f)]
    else:
        lunes = hoy - timedelta(days=hoy.weekday())
        dias = [ctx.fechas.index(lunes + timedelta(days=i)) for i in range(7) if lunes + timedelta(days=i) in ctx.fechas]
    ausente = {(a.persona, a.fecha) for a in e.ausencias}
    lineas = []
    for d in dias:
        f = ctx.fechas[d]
        personas = [quien] if quien else [p.nombre for p in ctx.empresa.plantilla]
        trabajan = [f"{n} {fmt(e.cuadrante[n][d])}" + (" (ausente)" if (n, f) in ausente else "") for n in personas if e.cuadrante[n][d]]
        libran = [n for n in personas if not e.cuadrante[n][d]]
        lineas.append(f"{nombre_dia(f)}: " + (", ".join(trabajan) or "nadie trabaja") + (f". Libran: {', '.join(libran)}" if libran else ""))
    return Resultado("\n".join(lineas), e, ir_a=ctx.fechas[dias[0]].isoformat())


def ver_horas(e: Estado, hoy: date, persona: str = "") -> Resultado:
    ctx = contexto(e.boe, e.ausencias)
    n = persona_de(ctx, persona)
    if not n:
        return Resultado(f"No hay nadie llamado «{persona}» en la plantilla.", e)
    p = next(x for x in ctx.empresa.plantilla if x.nombre == n)
    total = sum(horas(tuple(t)) for t in e.cuadrante[n] if t)
    semanas = [sum(horas(tuple(e.cuadrante[n][d])) for d in s if e.cuadrante[n][d]) for s in ctx.semanas()]
    return Resultado(f"{n}: contrato de {ctx.horas_contrato(p)} h a la semana. En el periodo lleva {total} h de un objetivo de "
                     f"{ctx.objetivo_periodo(p)} h (saldo anual de partida {p.saldo_horas:+} h). Por semanas: {', '.join(map(str, semanas))} h.", e)


def ver_incumplimientos(e: Estado, hoy: date) -> Resultado:
    ctx = contexto(e.boe, e.ausencias)
    incs = [i for i in comprobar(ctx, tuplas(e.cuadrante), pagadas(e)) if not i.pactado(e.acuerdos)]
    if not incs:
        return Resultado("El cuadrante cumple el convenio y cubre todas las horas.", e)
    lineas = [f"- {i.persona + ': ' if i.persona else ''}{i.mensaje}"
              f" ({', '.join(nombre_dia(ctx.fechas[d]) for d in i.dias[:3])}){cita(i.regla)}" for i in incs[:12]]
    return Resultado(f"{len(incs)} incumplimientos o huecos:\n" + "\n".join(lineas), e)


def explicar_regla(e: Estado, hoy: date, tipo: str = "") -> Resultado:
    """Las reglas del convenio activo y del Estatuto del tipo que elige el modelo de un enum. Buscar
    por palabras fallaba: «horas entre turnos» no llegaba al ET 34.3."""
    ctx = contexto(e.boe)
    reglas = [r for r in ctx.reglas if r.tipo == tipo]
    if not reglas:
        return Resultado("Ni el convenio activo ni el Estatuto tienen una regla de ese tipo que se aplique aquí.", e)
    pacto = {"no": "No se puede pactar.", "individual": "Se puede pactar con la persona.", "colectivo": "Solo con acuerdo colectivo."}
    return Resultado("Lo que dicen el convenio y el Estatuto:\n" + "\n".join(
        f"- {r.cita.articulo if r.origen == 'estatuto' else 'art. ' + r.cita.articulo}: «{r.cita.texto}» {pacto[r.pactable]}"
        for r in reglas), e)


def marcar_ausencia(e: Estado, hoy: date, persona: str = "", dia: str = "hoy", hasta_dia: str = "", horas_: str = "",
                    motivo: str = "otro", aviso: str | None = None, imprevista: bool | None = None) -> Resultado:
    """La ausencia se aplica y el solver la cubre moviendo lo mínimo. Las ausencias de antes ya están cubiertas: van en el contexto."""
    ctx = contexto(e.boe, e.ausencias)
    n = persona_de(ctx, persona)
    if not n:
        return Resultado(f"No hay nadie llamado «{persona}» en la plantilla." if persona else "Falta decir quién.", e)
    inicio = fecha_de(dia or "hoy", hoy)
    fin = fecha_de(hasta_dia, hoy, inicio) if hasta_dia else inicio
    if not inicio or not fin or fin < inicio:
        return Resultado(f"No entiendo los días ({dia} a {hasta_dia}).", e)
    fechas = [inicio + timedelta(days=i) for i in range((fin - inicio).days + 1)]
    if fuera := [f for f in fechas if f not in ctx.fechas]:
        return Resultado(f"El {nombre_dia(fuera[0])} está fuera del cuadrante.", e)
    desde = hasta = None
    if horas_:
        t = turno_de(ctx, horas_ if re.search(r"\d.*\d", horas_) or not re.search(r"\d", horas_)
                     else f"{re.search(r'\d+', horas_)[0]}-{ctx.empresa.apertura.hasta}")
        if isinstance(t, str) or t is None:
            return Resultado(f"No entiendo las horas «{horas_}».", e)
        desde, hasta = t[0], min(t[1], 24)
    aviso_f = date.fromisoformat(aviso) if aviso else hoy
    nuevas = [Ausencia(persona=n, fecha=f, desde=desde, hasta=hasta, motivo=motivo, aviso=min(aviso_f, f),
                       imprevista=motivo != "vacaciones" if imprevista is None else imprevista) for f in fechas]
    rp = replanificar(ctx, tuplas(e.cuadrante), nuevas, acuerdos=e.acuerdos)
    if not rp.cuadrante:
        return Resultado(f"El solver no encuentra forma de cubrirlo ({rp.estado}).", e)
    clases = dict(e.clases)
    for c in rp.cambios:  # las horas añadidas, pintadas por clase en el orden en que se reparten
        antes = set(range(*c.antes)) if c.antes else set()
        nuevas_h = [h for h in range(*c.despues) if h not in antes]
        orden = [cl for cl, h in c.horas.items() for _ in range(h)]
        clases[f"{c.persona}|{c.dia}"] = {**clases.get(f"{c.persona}|{c.dia}", {}), **dict(zip(nuevas_h, orden))}
    nuevo = e.model_copy(update={"cuadrante": listas(rp.cuadrante), "ausencias": e.ausencias + nuevas, "clases": clases})
    cuando = nombre_dia(inicio) + (f" al {nombre_dia(fin)}" if fin > inicio else "")
    lineas = [f"{n} ausente ({motivo}) el {cuando}" + (f" de {desde} a {hasta}" if desde is not None else "") + ". Aplicado."]
    opciones = {c.persona: {o.clase: o for o in rp.opciones[c.persona]} for c in rp.cambios}
    for c in rp.cambios:
        detalle = ", ".join(f"{h} h {cl}{cita(opciones[c.persona][cl].regla)}" for cl, h in c.horas.items())
        lineas.append(f"- {c.persona} {nombre_dia(ctx.fechas[c.dia])}: {fmt(c.antes)} → {fmt(c.despues)} ({detalle})")
    if not rp.cambios:
        lineas.append("No hace falta mover a nadie: la cobertura sigue llegando.")
    if rp.sin_cubrir:
        lineas.append("Sin cubrir (nadie puede dentro del convenio con este preaviso): "
                      + ", ".join(f"{nombre_dia(ctx.fechas[d])} {h}-{h + 1}" for d, h, _ in rp.sin_cubrir))
    return Resultado("\n".join(lineas), nuevo, cambio=True, ir_a=inicio.isoformat(),
                     resaltar=[(c.persona, c.dia) for c in rp.cambios] + [(n, ctx.fechas.index(f)) for f in fechas])


def _editar(e: Estado, celdas: dict[tuple[str, int], tuple[int, int] | None], con_acuerdo: bool, que: str) -> Resultado:
    ctx = contexto(e.boe, e.ausencias)
    nuevo, nuevos, todos = editar_celdas(ctx, tuplas(e.cuadrante), celdas, e.acuerdos, pagadas(e))
    niveles = {i.nivel for i in nuevos}
    nivel = next((x for x in ("bloqueo", "acuerdo", "aviso") if x in niveles), "ok")
    def detalle(nivel_: str) -> str:
        return "\n".join(f"- {i.persona + ': ' if i.persona else ''}{i.mensaje}{cita(i.regla)}" for i in nuevos if i.nivel == nivel_)
    ir = ctx.fechas[next(iter(celdas))[1]].isoformat()
    if nivel == "bloqueo":
        return Resultado(f"No se puede {que}: el convenio no lo permite y no se puede pactar.\n{detalle("bloqueo")}", e, nivel=nivel, incidencias=nuevos, ir_a=ir)
    if nivel == "acuerdo" and not con_acuerdo:
        quien = " y ".join(sorted({i.persona for i in nuevos if i.nivel == "acuerdo" and i.persona}))
        return Resultado(f"Para {que} hace falta el acuerdo de {quien}: el convenio deja pactarlo con la persona. "
                         f"¿Está de acuerdo? Si me dices que sí, lo aplico y queda registrado.\n{detalle("acuerdo")}",
                         e, nivel=nivel, incidencias=nuevos, ir_a=ir)
    pactados = [i for i in nuevos if i.nivel == "acuerdo"]
    clases = {k: v for k, v in e.clases.items() if tuple(k.split("|")) not in {(n, str(d)) for n, d in celdas}}
    estado = e.model_copy(update={
        "cuadrante": listas(nuevo), "clases": clases,
        "acuerdos": e.acuerdos + [Acuerdo(persona=i.persona, tipo=str(i.tipo), dias=list(i.dias), mensaje=i.mensaje) for i in pactados]})
    texto = f"Hecho: {que}." + (" Queda registrado el acuerdo de la persona." if pactados else "")
    # Ya aplicado, el nivel solo dice si quedan avisos: con "acuerdo" la web volvía a pedirlo.
    nivel = "aviso" if any(i.nivel == "aviso" for i in nuevos) else None
    if nivel == "aviso":
        texto += f" Avisos:\n{detalle('aviso')}"
    return Resultado(texto, estado, cambio=True, resaltar=list(celdas), nivel=nivel, incidencias=nuevos, ir_a=ir)


def cambiar_turno(e: Estado, hoy: date, persona: str = "", dia: str = "", turno: str = "", con_acuerdo: bool = False) -> Resultado:
    ctx = contexto(e.boe)
    n = persona_de(ctx, persona)
    f = fecha_de(dia, hoy)
    if not n:
        return Resultado(f"No hay nadie llamado «{persona}» en la plantilla." if persona else "Falta decir a quién.", e)
    if not f or f not in ctx.fechas:
        return Resultado(f"No entiendo el día «{dia}» o cae fuera del cuadrante.", e)
    t = turno_de(ctx, turno)
    if isinstance(t, str):
        return Resultado(t, e)
    d = ctx.fechas.index(f)
    if (list(t) if t else None) == e.cuadrante[n][d]:
        return Resultado(f"{n} ya tiene {fmt(t)} el {nombre_dia(f)}.", e)
    return _editar(e, {(n, d): t}, con_acuerdo, f"poner a {n} {fmt(t)} el {nombre_dia(f)} (antes {fmt(e.cuadrante[n][d])})")


def intercambiar_turnos(e: Estado, hoy: date, persona: str = "", otra_persona: str = "", dia: str = "", con_acuerdo: bool = False) -> Resultado:
    ctx = contexto(e.boe)
    a, b, f = persona_de(ctx, persona), persona_de(ctx, otra_persona), fecha_de(dia, hoy)
    if not a or not b:
        return Resultado(f"No encuentro a «{persona if not a else otra_persona}» en la plantilla.", e)
    if not f or f not in ctx.fechas:
        return Resultado(f"No entiendo el día «{dia}» o cae fuera del cuadrante.", e)
    d = ctx.fechas.index(f)
    ta, tb = e.cuadrante[a][d], e.cuadrante[b][d]
    celdas = {(a, d): tuple(tb) if tb else None, (b, d): tuple(ta) if ta else None}
    return _editar(e, celdas, con_acuerdo, f"intercambiar el {nombre_dia(f)} a {a} ({fmt(ta)}) y {b} ({fmt(tb)})")


def cambiar_convenio(e: Estado, hoy: date, convenio: str = "") -> Resultado:
    boe = CONVENIOS.get(normal(convenio).replace("contact centre", "contact center")) or (convenio if convenio.startswith("BOE-") else None)
    if not boe:
        return Resultado(f"No conozco el convenio «{convenio}». Hay: {', '.join(CONVENIOS)}.", e)
    if boe == e.boe:
        return Resultado("Ya está ese convenio.", e)
    nuevo = estado_inicial(boe)
    return Resultado(f"Convenio cambiado a {contexto(boe).convenio.nombre}. El cuadrante vuelve al de partida bajo sus reglas.", nuevo, cambio=True)


def ir_a(e: Estado, hoy: date, dia: str = "") -> Resultado:
    f = fecha_de(dia, hoy)
    ctx = contexto(e.boe)
    if not f or f not in ctx.fechas:
        return Resultado(f"«{dia}» no cae dentro del cuadrante.", e)
    return Resultado(f"Mostrando el {nombre_dia(f)}.", e, ir_a=f.isoformat())


ACCIONES = {f.__name__: f for f in (ver_cuadrante, ver_horas, ver_incumplimientos, explicar_regla, marcar_ausencia,
                                     cambiar_turno, intercambiar_turnos, cambiar_convenio, ir_a)}


def ejecutar(nombre: str, e: Estado, hoy: date, args: dict) -> Resultado:
    if nombre not in ACCIONES:
        return Resultado(f"No existe la acción {nombre}.", e)
    # 'horas' es también una función de este módulo: el parámetro se llama horas_.
    args = {("horas_" if k == "horas" else k): v for k, v in args.items() if v not in (None, "")}
    try:
        return ACCIONES[nombre](e, hoy, **args)
    except TypeError as x:
        return Resultado(f"Argumentos no válidos para {nombre}: {x}", e)

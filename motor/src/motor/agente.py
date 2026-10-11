"""Agente del panel lateral: el LLM elige qué herramienta usar con lo que pide el usuario.

Las herramientas son las mismas acciones que se hacen a mano en la hoja, y cada una pasa por la
misma validación (comprobador, solver, niveles del convenio). El modelo nunca calcula fechas ni
turnos: copia "el jueves" o "de tarde" y el código lo interpreta.

Medir modelos con el banco: uv run python -m motor.agente [modelo] [pensar]
"""

import difflib
import json
import re
import sys
import time
from collections.abc import Iterator
from datetime import date

import httpx

from motor.acciones import DIAS, HISTORIAL, Estado, contexto, ejecutar, normal
from motor.empresa import RAIZ, Contexto

OLLAMA = "http://localhost:11434/api/chat"

DIA = {"type": "string", "description": "El día como lo dice el usuario: 'hoy', 'mañana', 'jueves', 'el 12', 'lunes que viene'."}
PERSONA = {"type": "string", "description": "Nombre de una persona de la plantilla."}
ACUERDO = {"type": "boolean", "description": "Solo true si el usuario ha confirmado que la persona está de acuerdo."}


def herramienta(nombre: str, descripcion: str, props: dict, requeridos: list[str] = ()) -> dict:
    return {"type": "function", "function": {"name": nombre, "description": descripcion, "parameters": {
        "type": "object", "properties": props, "required": list(requeridos)}}}


HERRAMIENTAS = [
    herramienta("ver_cuadrante", "Ver quién trabaja y en qué turno. Filtra por persona, por día o por los dos.",
                {"persona": PERSONA, "dia": DIA}),
    herramienta("ver_horas", "Horas trabajadas, contrato y saldo de horas de una persona.",
                {"persona": PERSONA}, ["persona"]),
    herramienta("ver_incumplimientos", "Lista lo que incumple el convenio o deja huecos de cobertura en el cuadrante actual.", {}),
    herramienta("explicar_regla", "Busca en el convenio activo y el Estatuto la regla sobre un tema (descansos, horas extra, nocturnidad, preaviso...) para explicarla con su cita.",
                {"tema": {"type": "string"}}, ["tema"]),
    herramienta("marcar_ausencia", "Marca que una persona falta (baja, médico, vacaciones...) y busca quién la cubre sin saltarse el convenio.",
                {"persona": PERSONA, "dia": DIA,
                 "hasta_dia": {**DIA, "description": "Último día si son varios: 'hasta el viernes' da 'viernes'."},
                 "horas": {"type": "string", "description": "Solo si no falta el día entero: '9-11', 'mañana', 'tarde', 'desde las 18'."},
                 "motivo": {"type": "string", "enum": ["baja", "cita médica", "examen", "asunto propio", "vacaciones", "otro"]}},
                ["persona", "dia"]),
    herramienta("cambiar_turno", "Pone a una persona un turno un día, o la deja libre. Valida el convenio.",
                {"persona": PERSONA, "dia": DIA,
                 "turno": {"type": "string", "description": "'mañana', 'tarde', 'noche', 'libre' o horas como '9-17'."},
                 "con_acuerdo": ACUERDO},
                ["persona", "dia", "turno"]),
    herramienta("intercambiar_turnos", "Intercambia los turnos de dos personas un día.",
                {"persona": PERSONA, "otra_persona": PERSONA, "dia": DIA, "con_acuerdo": ACUERDO},
                ["persona", "otra_persona", "dia"]),
    herramienta("deshacer", "Deshace el último cambio (también si el usuario dice que no le gusta o que lo quite).", {}),
    herramienta("ir_a", "Muestra en la hoja un día o su semana.", {"dia": DIA}, ["dia"]),
    herramienta("cambiar_convenio", "Cambia el convenio colectivo con el que se planifica.",
                {"convenio": {"type": "string", "enum": ["grandes almacenes", "contact center", "dependencia"]}}, ["convenio"]),
]

def sistema(ctx: Contexto, hoy: date) -> str:
    nombres = ", ".join(p.nombre for p in ctx.empresa.plantilla)
    return f"""Eres el asistente de Cuadrante, un programa para que un jefe de equipo haga los horarios de su plantilla cumpliendo el convenio colectivo. Haces lo que te pidan dentro del programa usando las herramientas.

- Hoy es {DIAS[hoy.weekday()]} {hoy.day}/{hoy.month}/{hoy.year}. Convenio activo: {ctx.convenio.nombre}.
- Plantilla: {nombres}.
- El usuario escribe rápido y con faltas de ortografía (b por v, sin h, k por c): entiende lo que quiere decir ("vaja" es baja, "asta" es hasta). Los nombres pueden venir mal escritos; usa el de la plantilla que corresponda.
- Motivo de una ausencia: vacaciones solo si dice vacaciones; si no dice por qué, "otro".
- Para los días y los turnos copia lo que dice el usuario ("el jueves", "de tarde"); no calcules fechas.
- Si falta un dato imprescindible (quién o qué día), pregunta antes de actuar.
- Los cambios se aplican al momento y se pueden deshacer. Para cualquier dato del cuadrante o del convenio usa una herramienta: no inventes horarios, reglas ni soluciones.
- Sin herramienta solo respondes para preguntar un dato que falta o para decir que algo no es del programa, en una frase.
- Si te piden algo que no tiene que ver con los horarios del equipo (el tiempo, noticias, recetas, programar...), no lo hagas ni des esa información: responde en una frase que solo ayudas con el cuadrante.
- Responde en español, breve."""


def llamar(mensajes: list[dict], modelo: str, pensar: bool) -> dict:
    r = httpx.post(OLLAMA, timeout=300, json={
        "model": modelo, "messages": mensajes, "tools": HERRAMIENTAS, "stream": False, "think": pensar,
        "options": {"temperature": 0, "num_ctx": 8192},
    })
    r.raise_for_status()
    return r.json()["message"]


# --- Conversación ---

MUTAN = {"marcar_ausencia", "cambiar_turno", "intercambiar_turnos"}
SIN_RESPUESTA = "No te he entendido. ¿Me lo dices de otra forma?"
PIENSA_EN_TEXTO = re.compile(r"^\s*(okay|ok,|alright|let me|first,|hmm)|the user", re.I)


def turno_modelo(mensajes: list[dict], modelo: str) -> dict:
    """Una vuelta del modelo. Si en vez de actuar se pone a razonar en el texto (le pasa a qwen3
    sin razonamiento cuando hay herramientas), se repite con el razonamiento activado."""
    m = llamar(mensajes, modelo, False)
    if not m.get("tool_calls") and PIENSA_EN_TEXTO.search(m.get("content") or ""):
        m = llamar(mensajes, modelo, True)
    m.pop("thinking", None)
    m["content"] = re.sub(r"<think>.*?</think>", "", m.get("content") or "", flags=re.S).strip()
    return m


def descuadre(texto: str, llamadas: list[dict]) -> str | None:
    """Un número o un día de la semana que el usuario dijo y no llega a las acciones que cambian
    algo. Un modelo pequeño a veces se come "el 11" de "el miércoles 11", y eso, sin esta
    comprobación, se aplicaría a otro miércoles sin avisar."""
    if not llamadas:
        return None
    dicho = re.findall(r"\w+", normal(texto))
    pasado = normal(" ".join(str(v) for a in llamadas for v in a.values()))
    numeros = set(re.findall(r"\d+", pasado))
    for w in dicho:
        if w.isdigit() and w not in numeros:
            return w
    semana, palabras = [normal(d) for d in DIAS], re.findall(r"\w+", pasado)
    for w in dicho:
        if difflib.get_close_matches(w, semana, n=1, cutoff=0.8) and not difflib.get_close_matches(w, palabras, n=1, cutoff=0.8):
            return w
    return None


def conversar(estado: Estado, historial: list[Estado], mensajes: list[dict], texto: str, hoy: date,
              modelo: str = "qwen3:4b", pasos: int = 6) -> Iterator[dict]:
    """Ejecuta lo que pide el usuario. Va soltando eventos: una 'accion' por herramienta y un 'fin'."""
    ctx = contexto(estado.boe)
    mensajes = [*mensajes[-20:], {"role": "user", "content": texto}]
    resaltar, ir = [], None
    for _ in range(pasos):
        m = turno_modelo([{"role": "system", "content": sistema(ctx, hoy)}, *mensajes], modelo)
        mensajes.append(m)
        if not m.get("tool_calls"):
            break
        textos = []
        llamadas = [(c["function"]["name"], dict(c["function"].get("arguments") or {})) for c in m["tool_calls"]]
        falta = descuadre(texto, [a for n, a in llamadas if n in MUTAN])
        for nombre, args in llamadas:
            if falta and nombre in MUTAN:
                # No se ejecuta: el modelo vuelve a intentarlo con lo que dijo el usuario.
                mensajes.append({"role": "tool", "tool_name": nombre, "content":
                                 f"No ejecutado: el usuario dijo «{falta}» y no está en la llamada. Repítela copiando el día y la hora tal como los dijo."})
                continue
            if nombre == "deshacer":
                if historial:
                    estado, historial = historial[-1], historial[:-1]
                    res_texto, resaltar = "Deshecho el último cambio.", []
                else:
                    res_texto = "No hay nada que deshacer."
                nivel = None
            else:
                r = ejecutar(nombre, estado, hoy, args)
                if r.cambio:
                    historial = [*historial, estado][-HISTORIAL:]
                    resaltar = r.resaltar
                estado, res_texto, nivel, ir = r.estado, r.texto, r.nivel, r.ir_a or ir
                ctx = contexto(estado.boe)
            mensajes.append({"role": "tool", "tool_name": nombre, "content": res_texto})
            textos.append(res_texto)
            yield {"tipo": "accion", "nombre": nombre, "args": args, "texto": res_texto, "nivel": nivel}
        # El texto de cada acción lo escribe el código, con la cita literal. Que el modelo lo vuelva a
        # contar cuesta 10 s y, en las pruebas, le hacía inventar horarios y reglas.
        if textos:
            mensajes.append({"role": "assistant", "content": "\n\n".join(textos)})
            break
    else:
        mensajes.append({"role": "assistant", "content": "He llegado al máximo de pasos. Dime cómo sigo."})
    if not mensajes[-1].get("content"):
        mensajes[-1] = {"role": "assistant", "content": SIN_RESPUESTA}
    yield {"tipo": "fin", "respuesta": mensajes[-1].get("content", ""), "estado": estado.model_dump(mode="json"),
           "historial": [h.model_dump(mode="json") for h in historial], "mensajes": mensajes,
           "resaltar": resaltar, "ir_a": ir}


# --- Banco: demo/instrucciones.json ---

def casa(llamada: dict, esperada: dict) -> bool:
    """La llamada usa la herramienta esperada y sus argumentos contienen los esperados (sin tildes ni mayúsculas)."""
    if llamada["name"] != esperada["tool"]:
        return False
    args = {k: normal(str(v)) for k, v in (llamada.get("arguments") or {}).items()}
    for k, v in esperada.get("args", {}).items():
        opciones = v if isinstance(v, list) else [v]
        if not any(normal(str(o)) in args.get(k, "") for o in opciones):
            return False
    return True


def medir(modelo: str = "qwen3:4b", pensar: bool = False, boe: str = "BOE-A-2023-13740") -> None:
    from motor.empresa import cargar_convenio, cargar_empresa
    ctx = Contexto.crear(cargar_empresa(), cargar_convenio(boe))
    hoy = date(2026, 11, 9)
    casos = json.loads((RAIZ / "demo" / "instrucciones.json").read_text(encoding="utf-8"))
    bien, tiempos, por_tipo = 0, [], {}
    for caso in casos:
        t = time.perf_counter()
        msgs = [{"role": "system", "content": sistema(ctx, hoy)}, {"role": "user", "content": caso["texto"]}]
        m = llamar(msgs, modelo, True) if pensar else turno_modelo(msgs, modelo)
        tiempos.append(time.perf_counter() - t)
        llamadas = [c["function"] for c in m.get("tool_calls") or []]
        espera, texto = caso["espera"], (m.get("content") or "").lower()
        # Vale cualquiera de las alternativas: la primera llamada, o una respuesta sin llamadas que
        # rechaza (habla del cuadrante o los horarios) o pregunta (lleva '?').
        ok = any(
            (not llamadas and "?" in texto) if e == "pregunta"
            else (not llamadas and any(p in texto for p in ("cuadrante", "horario", "turno"))) if e == "rechazo"
            else bool(llamadas) and casa(llamadas[0], e)
            for e in espera)
        bien += ok
        tipo = por_tipo.setdefault(caso["tipo"], [0, 0])
        tipo[0] += ok; tipo[1] += 1
        if not ok:
            print(f"FALLA [{caso['tipo']}] {caso['texto']!r}\n   espera  {espera}\n   obtiene {llamadas or m.get('content', '')[:160]!r}")
    tiempos.sort()
    print(f"\n{modelo} pensar={pensar}: {bien}/{len(casos)} bien. "
          + " · ".join(f"{k} {a}/{n}" for k, (a, n) in por_tipo.items())
          + f". Latencia mediana {tiempos[len(tiempos) // 2]:.1f} s, máxima {tiempos[-1]:.1f} s.")


if __name__ == "__main__":
    a = sys.argv[1:]
    medir(a[0] if a else "qwen3:4b", len(a) > 1 and a[1] == "pensar")

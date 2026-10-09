"""Valida un reglas/<BOE-ID>.json contra el texto del convenio.

Tres capas, como en radar-licitaciones:
1. Forma: el esquema de `reglas.py` (pydantic).
2. La cita existe: el fragmento está, literal, en el artículo citado.
3. El dato sale de la cita: cada cifra de la regla aparece en el fragmento,
   en número o en letra ("1764", "1.764", "mil setecientas sesenta y cuatro").

Uso:
  uv run python -m motor.validar reglas/BOE-A-2023-13741.json
  uv run python -m motor.validar --esquema      # JSON Schema para el agente
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

from pydantic import ValidationError

from motor.reglas import Regla, ReglasConvenio, TipoRegla

RAIZ = Path(__file__).resolve().parents[3]
CONVENIOS = RAIZ / "convenios"

ENCABEZADO = re.compile(r"^## Art[íi]culo\s+(\d+(?:\s*bis)?)\b", re.IGNORECASE)


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("«", '"').replace("»", '"').replace("“", '"').replace("”", '"')
    return " ".join(s.split())


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def articulos(boe_id: str) -> dict[str, str]:
    """Texto de cada artículo del convenio, por número ('22', '27 bis')."""
    md = (CONVENIOS / f"{boe_id}.md").read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}
    actual = None
    for linea in md.splitlines():
        m = ENCABEZADO.match(linea)
        if m:
            actual = " ".join(m.group(1).lower().split())
            out[actual] = []
        elif linea.startswith("#"):
            actual = None
        elif actual:
            out[actual].append(linea)
    return {k: "\n".join(v) for k, v in out.items()}


# --- Números en letra (0 a 9999, masculino y femenino) ---

UNIDADES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
            "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete",
            "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés",
            "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve"]
DECENAS = {30: "treinta", 40: "cuarenta", 50: "cincuenta", 60: "sesenta", 70: "setenta",
           80: "ochenta", 90: "noventa"}
CENTENAS = {100: "ciento", 200: "doscientos", 300: "trescientos", 400: "cuatrocientos",
            500: "quinientos", 600: "seiscientos", 700: "setecientos", 800: "ochocientos",
            900: "novecientos"}


def _menor_cien(n: int) -> str:
    if n < 30:
        return UNIDADES[n]
    d, u = divmod(n, 10)
    return DECENAS[d * 10] + ("" if u == 0 else " y " + UNIDADES[u])


def _menor_mil(n: int) -> str:
    if n == 100:
        return "cien"
    c, r = divmod(n, 100)
    partes = [CENTENAS[c * 100]] if c else []
    if r:
        partes.append(_menor_cien(r))
    return " ".join(partes)


def en_letra(n: int) -> str:
    if n < 1000:
        return _menor_mil(n)
    m, r = divmod(n, 1000)
    cabeza = "mil" if m == 1 else _menor_mil(m) + " mil"
    return cabeza + ("" if r == 0 else " " + _menor_mil(r))


def formas(valor: float) -> set[str]:
    """Maneras en que una cifra puede aparecer escrita en el texto."""
    if valor == 1.5:
        return {"1,5", "1.5", "día y medio", "uno y medio"}
    if valor != int(valor):
        s = f"{valor}".rstrip("0")
        return {s, s.replace(".", ",")}
    n = int(valor)
    letra = en_letra(n)
    # "mil setecientas sesenta y cuatro horas", "veintiuna semanas", "veintiún días"
    fem = re.sub(r"uno\b", "una", letra.replace("ientos", "ientas"))
    apocope = re.sub(r"uno\b", "un", letra).replace("veintiun", "veintiún")
    out = {str(n), letra, fem, apocope}
    if n >= 1000:
        out.add(f"{n:,}".replace(",", "."))
    return out


def aparece(valor: float, texto: str, en_dias: bool = False) -> bool:
    """Si la cifra son días y es múltiplo de 7, vale también en semanas ("cuatro semanas" = 28)."""
    t = sin_tildes(normalizar(texto))
    candidatos = [(f, "") for f in formas(valor)]
    if en_dias and valor and valor % 7 == 0:
        candidatos += [(f, r"\s+semanas?") for f in formas(valor / 7)]
    for f, sufijo in candidatos:
        f = sin_tildes(normalizar(f))
        # Bordes de palabra para que "8" no case con "18" ni "doce" con "doceavo".
        if re.search(rf"(?<![\w.,]){re.escape(f)}(?![\w]|[.,]\d){sufijo}", t):
            return True
    return False


def hora_aparece(hhmm: str, texto: str) -> bool:
    h, m = hhmm.split(":")
    variantes = {f"{h}:{m}", f"{int(h)}:{m}", f"{h}.{m}", f"{int(h)}.{m}"}
    if m == "00":
        variantes |= {f"las {int(h)}", f"las {h}"}
    t = normalizar(texto)
    return any(v in t for v in variantes)


# --- Validación ---


def comprobar(regla: Regla, arts: dict[str, str]) -> list[str]:
    """Lista de fallos de una regla; vacía si pasa."""
    fallos = []
    if regla.origen == "estatuto":
        return ["las reglas del Estatuto las pone el código, no el convenio"]
    for cita in filter(None, (regla.cita, regla.cita_pacto)):
        base = " ".join(cita.articulo.lower().split(".")[0].split())  # "30.3" -> "30"
        if base not in arts:
            return [f"el artículo {cita.articulo} no existe en el convenio"]
        if normalizar(cita.texto) not in normalizar(arts[base]):
            return [f"la cita no está literal en el artículo {base}"]
    if regla.cita_pacto:
        pacto = normalizar(regla.cita_pacto.texto)
        if not re.search(r"acuerd|pact", pacto):
            fallos.append("cita_pacto no habla de acuerdo ni de pacto")
        elif regla.pactable == "individual" and not re.search(
            r"individual|las partes|el personal|la persona trabajadora", pacto
        ):
            fallos.append("cita_pacto no permite el acuerdo individual")
    texto = regla.cita.texto
    for campo in ("valor", "valor_max", "ventana_dias"):
        v = getattr(regla, campo)
        en_dias = campo == "ventana_dias" or regla.unidad == "dias"
        if v is not None and not aparece(v, texto, en_dias):
            fallos.append(f"{campo}={v:g} no aparece en la cita")
    for campo in ("desde", "hasta"):
        v = getattr(regla, campo)
        if v is not None and not hora_aparece(v, texto):
            fallos.append(f"{campo}={v} no aparece en la cita")
    return fallos


def validar(ruta: Path) -> bool:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    try:
        convenio = ReglasConvenio.model_validate(datos)
    except ValidationError as e:
        print(f"FORMA: {e}")
        return False
    arts = articulos(convenio.boe)
    ok = True
    for i, regla in enumerate(convenio.reglas):
        fallos = comprobar(regla, arts)
        marca = "ok " if not fallos else "MAL"
        extra = f" [{regla.condicion}]" if regla.condicion else ""
        valor = f"{regla.valor:g}" if regla.valor is not None else (regla.turno or "")
        print(f"{marca} #{i:02d} {regla.tipo.value:32} {valor:>8}  art. {regla.cita.articulo}{extra}")
        for f in fallos:
            print(f"      - {f}")
        ok &= not fallos
    otras = sum(r.tipo == TipoRegla.OTRA for r in convenio.reglas)
    print(f"\n{len(convenio.reglas)} reglas, {otras} 'otra'. {'Todo valida.' if ok else 'Hay reglas que no validan.'}")
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--esquema"]:
        print(json.dumps(ReglasConvenio.model_json_schema(), ensure_ascii=False, indent=2))
    else:
        sys.exit(0 if all(validar(Path(p)) for p in sys.argv[1:]) else 1)

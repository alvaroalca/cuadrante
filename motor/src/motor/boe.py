"""Baja un convenio del BOE en XML y lo pasa a markdown, un encabezado por artículo.

El XML del BOE ya trae la estructura marcada (clases `capitulo_num`, `articulo`,
`parrafo`...), así que no hace falta conversor de PDF. El markdown resultante es lo
que lee el agente lector-convenio, y su numeración de artículos es la que se cita.

Uso: uv run python -m motor.boe BOE-A-2023-13741 [...]
"""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[3]
CACHE = RAIZ / "data" / "boe"
SALIDA = RAIZ / "convenios"
URL = "https://www.boe.es/diario_boe/xml.php?id={id}"

ARTICULO = re.compile(r"^Art[íi]culo\s+\d+", re.IGNORECASE)


def descargar(boe_id: str) -> Path:
    destino = CACHE / f"{boe_id}.xml"
    if not destino.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        r = httpx.get(URL.format(id=boe_id), timeout=60)
        r.raise_for_status()
        destino.write_bytes(r.content)
    return destino


def texto(el: ET.Element) -> str:
    return " ".join("".join(el.itertext()).split())


def tabla(el: ET.Element) -> list[str]:
    filas = []
    for tr in el.iter("tr"):
        celdas = [texto(c).replace("|", "/") for c in tr if c.tag in ("td", "th")]
        if celdas:
            filas.append("| " + " | ".join(celdas) + " |")
    if not filas:
        return []
    # Separador tras la primera fila para que sea tabla markdown; con rowspan/colspan
    # las columnas pueden no cuadrar, pero el contenido de cada celda se conserva.
    ncol = filas[0].count("|") - 1
    return [filas[0], "|" + " --- |" * ncol, *filas[1:], ""]


def convertir(xml_path: Path) -> str:
    raiz = ET.parse(xml_path).getroot()
    meta = raiz.find("metadatos")
    boe_id = meta.findtext("identificador")
    lineas = [
        "---",
        f"boe: {boe_id}",
        f"titulo: \"{meta.findtext('titulo')}\"",
        f"publicado: {meta.findtext('fecha_publicacion')}",
        f"pdf: {meta.findtext('url_pdf')}",
        "---",
        "",
    ]
    capitulo_pendiente = None
    for el in raiz.find("texto"):
        clase = el.get("class", "")
        if el.tag == "table":
            lineas += tabla(el)
            continue
        t = texto(el)
        if not t:
            continue
        if clase == "capitulo_num":
            capitulo_pendiente = t
        elif clase == "capitulo_tit":
            lineas += [f"# {capitulo_pendiente or ''} {t}".replace("#  ", "# "), ""]
            capitulo_pendiente = None
        elif clase == "articulo" and ARTICULO.match(t):
            lineas += [f"## {t}", ""]
        elif clase in ("articulo", "seccion", "centro_redonda", "titulo_num", "titulo_tit"):
            lineas += [f"### {t}", ""]
        else:
            lineas += [t, ""]
    return "\n".join(lineas)


def main(ids: list[str]) -> None:
    SALIDA.mkdir(exist_ok=True)
    for boe_id in ids:
        md = convertir(descargar(boe_id))
        (SALIDA / f"{boe_id}.md").write_text(md, encoding="utf-8")
        n = sum(1 for l in md.splitlines() if l.startswith("## "))
        print(f"{boe_id}: {n} artículos")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])

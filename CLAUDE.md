# CLAUDE.md: Cuadrante

Planificador de turnos que cumple el convenio colectivo. Se elige un convenio al entrar, la app carga sus reglas y un solver monta el cuadrante del mes. Ante una baja o una indisponibilidad, replanifica moviendo lo mínimo, y cada regla que aplica lleva la cita del artículo del que sale.

Pieza de portfolio de software a medida: se hace, se graba el reel y queda el repo público. Corre en local, sin despliegue. Estado vivo en `docs/STATUS.md`.

## Stack

- `motor/`: Python 3.13 con uv. OR-Tools CP-SAT (solver) + FastAPI. CP-SAT no tiene binding oficial para Node, por eso el backend es Python.
- `web/`: React + Vite + TS.
- Sin base de datos: reglas, plantilla demo y cuadrantes son JSON.
- LLM en la app: qwen3.5:4b por Ollama (`MODELO` en `motor/agente.py`), como asistente del panel lateral con poder sobre todo el programa (decisiones del 11/10/2026). El modelo es intercambiable: para la demo basta con que el guion del reel funcione, no se afina más (Álvaro, 12/10/2026).
- Arrancar: `cd motor && uv run uvicorn motor.api:app --reload` y `cd web && npm run dev` (proxy `/api` a :8000). Los cuadrantes de partida se cachean en `demo/cuadrantes/`; si cambian la ficha o las reglas, se borran y se regeneran (hasta 60 s por convenio).

## Decisiones cerradas (09/10/2026)

- **Leer el convenio es un paso de implantación, no de la app.** Lo hace el agente `.claude/agents/lector-convenio.md` con un modelo bueno (Claude), lo revisa una persona y queda versionado en `reglas/<BOE-ID>.json`. El agente es genérico: para un cliente nuevo se pasa por su convenio y se revisa el JSON, el agente no se toca.
- **Fuente: el XML del BOE**, no PDF. `uv run python -m motor.boe <BOE-ID>` lo baja a `data/boe/` (fuera de git) y escribe `convenios/<BOE-ID>.md` con un `## Artículo N.` por artículo. Esa numeración es la que se cita.
- **Esquema cerrado de reglas**: el tipo de regla es un enum con opción de escape; el agente no inventa tipos. El código valida que la cita existe en el artículo y que la cifra está en la cita.
- **Lo que el convenio no dice lo pone el Estatuto de los Trabajadores por código** (mínimos legales, p. ej. 12 h entre jornadas del art. 34.3), marcado como `origen: estatuto`.
- **Las decisiones las toma el solver**, nunca el LLM. El LLM elige la acción y copia lo que dice el usuario ("el jueves", "de tarde", "marat"); el código lo interpreta y cada acción pasa por el comprobador o el solver. Explica el resultado con la cita del convenio activo.
- **Replanificar con mínimo cambio**: una baja penaliza mover a quien no hace falta mover; no se rehace el mes.
- **Demo: un equipo, varios convenios.** La misma plantilla de 15 personas y la misma cobertura bajo cada convenio, para que al cambiar de convenio solo cambien las reglas.
- **Rejilla de 0 a 24 h por día** (como el Excel de horarios de Decathlon). El solver planifica la cobertura de la demo, mañana y tarde los 7 días; la noche solo aparece si alguien la pone a mano.
- **Ediciones a mano validadas en vivo, con tres niveles según el campo `pactable` de cada regla**: `individual` → aviso y confirmar con acuerdo de la persona (queda registrado); `colectivo` → bloqueo salvo acuerdo colectivo cargado; `no` → bloqueo con cita. Los mínimos del Estatuto nunca son pactables (ET 3.5: derecho necesario, la persona no puede renunciar a ellos). Trabajar de noche no está prohibido: ET 36.1 limita el promedio a 8 h.
- **Modelo por horas**: cobertura por hora (franjas de la ficha) y turnos continuos de 4, 6 u 8 h que empiezan en punto, uno al día por persona. Contratos por horas semanales (`completa` = la del convenio, hoy 38 h en los tres).
- **Lo obligatorio es la jornada anual** (Álvaro, 09/10/2026): semanas y periodos se desvían y la diferencia va al `saldo_horas` de cada persona, que se recupera a lo largo del año. El solver se acerca al objetivo del periodo (contrato menos saldo) dentro de dos márgenes de la empresa (`margen_semanal_horas`, `margen_periodo_horas`): son política, no ley. Exigir horas exactas por semana hacía imposible contact center (1 libre en cada 7 días + 2 fines de semana libres al mes + 5 días por semana).
- **Horas de más**: los parciales hacen complementarias (ET 12.5: pactadas con pacto escrito y 3 días de preaviso salvo convenio; voluntarias si son indefinidos; ambas solo con contrato de 10 h o más) y nunca extraordinarias (ET 12.4.c). Las completas, extraordinarias, como último recurso. Alternativa sin coste: redistribuir (trabajar más ahora y recuperar después), que es distribución irregular.
- **Convenios de la demo** (estatales, BOE 09/06/2023): grandes almacenes `BOE-A-2023-13740`, contact center `BOE-A-2023-13741`, dependencia `BOE-A-2023-13742`.

## Decisiones cerradas (11/10/2026)

- **Asistente con poder sobre el programa** (Álvaro): como el panel de IA de VS Code. Se puede trabajar a mano sin él o solo con él. Instrucciones detalladas o vagas y con faltas de ortografía; lo que no es del programa (el tiempo, recetas...) no lo contesta. Sus herramientas son las acciones de `motor/acciones.py`, y la web hace lo de la mano por esas mismas acciones (`/api/accion`): una sola vía.
- **Actúa y se deshace** (Álvaro): cada acción se aplica al momento con historial para deshacer. Una ausencia replanifica y aplica. Lo que necesita acuerdo individual solo se aplica si el usuario confirma que la persona está de acuerdo; un bloqueo, nunca.
- **Modelo medido, no supuesto**: banco `demo/instrucciones.json` (`uv run python -m motor.agente`). qwen3:4b 39/41 pero 13 s de mediana (razona en inglés dentro del texto aunque se le pida `think: false`, también con Ollama 0.40 y `/no_think`); qwen3.5:4b 38/41 en 3,5 s (máxima 4,4 s), elegido por la latencia; qwen3:8b inventa personas. Si el modelo razona en el texto en vez de llamar a una herramienta, esa vuelta se repite con razonamiento.
- **Estilo**: señalética del metro de Nueva York (banda negra, letra blanca, Archivo). El color lo pone la clase de la hora, no el turno: normal azul A/C/E, nocturna (22-6) morado 7, complementaria verde 4/5/6, extraordinaria naranja B/D/F, redistribución amarillo N/Q/R, ausencia rojo 1/2/3. Lo último que cambió va con contorno discontinuo.

## Gotchas

- Las cifras del convenio pueden venir en letra ("mil setecientas sesenta y cuatro horas", contact center art. 22). El validador de cifras tiene que normalizarlas.
- Las reglas tienen excepciones en el mismo artículo (contact center art. 22: 1.764 h, pero 1.597 h si la empresa paga por debajo de tablas). El esquema necesita sitio para la condición.

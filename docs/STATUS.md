# STATUS: Cuadrante

## 09/10/2026: arranque

- Repo creado (`motor/` Python + uv con OR-Tools 9.15, `web/` React + Vite + TS). Sin remoto.
- `motor/src/motor/boe.py`: baja el XML del BOE y lo pasa a markdown por artículos. Los tres convenios de la demo ya están en `convenios/` (grandes almacenes 103 artículos, contact center 95, dependencia 68).
- `motor/src/motor/reglas.py`: esquema cerrado de 18 tipos de regla (17 + `otra` de escape), con condición, escalones por año y cita. Mínimos del Estatuto (arts. 34.1, 34.3, 37.1, 34.2) con su texto literal del BOE consolidado. `efectivas(convenio, año)` decide qué aplica el solver: gana el escalón vigente, el convenio sustituye al Estatuto en el tipo que regula y las reglas con condición no entran.
- Probado a mano con reglas reales de grandes almacenes y contact center.
- Campo `pactable` (individual / colectivo / no) con `cita_pacto` obligatoria, y regla de nocturnidad del ET 36.1.
- `motor/src/motor/validar.py`: forma (pydantic), cita literal en el artículo, cifra dentro de la cita (en número, con punto de miles o en letra, en masculino y femenino, más "día y medio") y que la cita de pacto hable de acuerdo y del tipo declarado. Controles negativos: 6 reglas buenas pasan y las 6 trampas (cifra cambiada, cita retocada, artículo inexistente, hora cambiada, regla del Estatuto colada, pacto individual sobre texto colectivo) fallan por su motivo.
- Agente `.claude/agents/lector-convenio.md` (opus). Se lanza con `claude -p "Lee el convenio <BOE-ID> ..." --agent lector-convenio`.

- **Los tres `reglas/*.json` hechos y revisados**: 61 reglas (18 + 21 + 22), todas con la cita y la cifra comprobadas por el validador. Dos pasadas del agente, de 2 a 4 min y de 0,6 a 1 $ equivalentes por convenio. La primera destapó tres huecos del esquema y del validador (semanas, pausa con solo mínimo, descripciones de tipo que no llegaban al esquema exportado). En la revisión humana se corrigieron a mano 2 de las 61: contact center #04 ("3 días en 14" estaba como descanso semanal) y dependencia #10 (una excepción puesta como condición, que el solver habría descartado; de ahí el campo `excepto`).
- Las jornadas anuales de dependencia, los fines de semana y domingos de grandes almacenes llevan condición (ámbito, zona de apertura, días de promedio): sin una ficha de empresa que diga qué condiciones cumple, el solver no las aplica.
- Contact center 26.3: solo se puede cambiar el horario al 20 % de la plantilla y con una semana de antelación. Para una baja de mañana, la replanificación tendrá que proponer voluntarios (acuerdo individual) en vez de imponer cambios.

- **Primer cuadrante.** `demo/empresa.json`: 15 personas a jornada completa, mañana 7-15 y tarde 15-23, cobertura 5+5 entre semana y 4+3 el fin de semana, del 2 al 29/11/2026, y las condiciones que cumple bajo cada convenio (texto literal del JSON de reglas). `efectivas` activa las condicionadas de la ficha, que ganan a la general del mismo tipo.
  - `empresa.py`: calendario, prorrata de límites por mes o año al periodo y jornada del periodo (la anual entre las semanas efectivas del año, sin 30 días de vacaciones ni 14 festivos; prorratear entre 365 días daría 4 días por semana).
  - `cumplimiento.py`: comprobador independiente del solver; cada incumplimiento lleva su regla (cita y pactable). Es el que validará las ediciones a mano.
  - `solver.py`: CP-SAT con cada regla como restricción dura y objetivo de reparto justo de fines de semana y tardes. Óptimo en menos de 1 s en los tres convenios, con **0 incumplimientos** según el comprobador.
  - Control negativo: con errores inyectados (tarde seguida de mañana, 11 días seguidos, un mes entero sin librar, huecos de cobertura) el comprobador los caza en los tres convenios, cada uno con las reglas de su convenio.
  - Sin implementar todavía: descanso compensatorio por festivo (la demo no tiene festivos) y nocturnidad (ningún turno llega a 3 h nocturnas).

- **Modelo por horas y contratos mixtos** (petición de Álvaro): 8 completas, 4 a 30 h y 3 a 12 h, con pactos de complementarias variados (indefinido o no, con pacto o sin él) para que la app tenga que explicar a quién propone. Cobertura por hora: 4 personas de 7 a 23 entre semana y 3+3 el fin de semana (con 4 por la mañana contact center no llega: cada persona trabaja como mucho 2 de los 4 fines de semana). Turnos de 4, 6 u 8 h.
- Tres tipos de regla nuevos (complementarias pactadas y voluntarias en %, preaviso) con los mínimos del ET 12.5. El agente solo **añadió** reglas a los JSON revisados, sin tocar ninguna: grandes almacenes 60 % y 30 % (art. 10), dependencia 30 % y 7 días, o 48 h si la necesidad no estaba prevista (art. 18.6); contact center no las regula.
- Saldo anual: el contrato no se exige exacto ni por semana ni por periodo (ver CLAUDE.md). Con eso, los tres convenios dan cuadrante con 0 incumplimientos (dependencia óptimo en 34 s; grandes almacenes y contact center, solución válida en el límite de 60 s). Control negativo por horas repetido: caza todo lo inyectado.
- El solver acepta una `pista` (un cuadrante de partida que repara): es la base de la replanificación.
- Pendiente de afinar: la condición de 22 domingos de grandes almacenes es por persona ("más de tres días de promedio") y se aplica a toda la plantilla, también a los de 12 h; es más estricto que el convenio.

- **Ausencias y replanificación** (`replanificar.py`). Una ausencia es persona, día, horas opcionales, motivo y fecha de aviso. El turno de quien falta se queda (sus horas cuentan para el contrato, justificadas) pero no cubre. Mínimo cambio: todo fijo salvo los días de la ausencia, y esos días solo se añaden horas (alargar un turno o dar uno a quien libra). Cada hora añadida tiene clase legal, de la más barata a la más cara: redistribución (al saldo; preaviso ET 34.2, 5 días, o el del convenio si es mayor), complementarias voluntarias, pactadas (preaviso del convenio, y el de imprevistos si la ficha lo activa: dependencia 48 h) y extras (solo completas). En contact center, los cambios impuestos (redistribución, pactadas) no pasan del 20 % de la plantilla. Cada persona sale con qué puede hacer y por qué no lo demás.
  - Misma baja con un día de aviso: grandes almacenes la cubre Óscar (8 h voluntarias, bolsa del 30 % del convenio), contact center Sergio (8 h, el 15 % del ET no le llega a Óscar) y dependencia la parte entre Elena y Óscar (4 + 4). Con 2 días de aviso, dependencia ya deja pactadas; con 6, grandes almacenes redistribuye sin coste (Lucía trabaja su libre y suma 8 h al saldo). 0 incumplimientos en todos.
  - Los cuadrantes de partida se guardan en `demo/cuadrantes/<BOE-ID>.json` (generarlos cuesta hasta 60 s; replanificar, unos segundos).
- Interpretación a revisar: para redistribuir en contact center se usa el preaviso de publicación de horarios (14 días, art. 26.3) en vez de la semana que el mismo artículo pide para modificarlos. Es lo más estricto.

- **Web y API.** `motor/src/motor/api.py` (FastAPI): convenios, reglas efectivas y no aplicadas, hoja con el cuadrante de partida, comprobar un cuadrante y replanificar. `web/` (React + Vite, proxy `/api` a :8000): diálogo de entrada para elegir convenio (`?convenio=BOE-…` lo salta, para grabar), hoja de 0 a 24 h por día y vista de semana, pestañas de día y flechas de semana, barra de fórmulas que enseña el turno y la cita de la regla, panel de tareas con las reglas del convenio y del Estatuto (nota amarilla con la cita literal al pasar el ratón), y el flujo de ausencia: clic derecho o menú, diálogo con horas y fecha de aviso, propuesta con hormigas y "quién puede qué", aplicar o descartar.
  - Referencia visual elegida por Álvaro: hoja de cálculo de escritorio de la época Office 2000/XP (cromo gris, retícula, paleta clásica de 56 colores, comentarios de celda, hormigas de copiar). Fuentes Archivo Narrow y Azeret Mono.
  - Recorrido probado con Edge headless (playwright-core desde PowerShell; desde Bash Edge no arranca): ausencia de Luis el martes 10 en dependencia → Elena 11-15 e Irene 7-11, 4 h voluntarias cada una, 0 incumplimientos tras aplicar.

## Siguiente

1. Ediciones a mano en la rejilla con los tres niveles de aviso (pactable individual, colectivo, no), validadas con `/api/comprobar`.
2. README con cómo implantar un convenio nuevo (agente, revisión, ficha) y cómo arrancar.
3. Traducción de frases con qwen ("Carmen de baja el martes") y banco de frases para medirla.
4. Reel y ficha del portfolio.

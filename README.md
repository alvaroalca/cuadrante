# Cuadrante

Planificador de turnos que cumple el convenio colectivo. Se elige el convenio de la plantilla, la app carga sus reglas y un solver monta el cuadrante del mes. Cuando alguien falta, replanifica moviendo lo mínimo y dice qué clase de hora pide a cada persona (redistribución, complementarias, extraordinarias). Cada regla que se aplica lleva la cita literal del artículo del que sale.

La demo trae una plantilla de 15 personas con contratos mixtos y tres convenios estatales publicados en el BOE del 9/06/2023: grandes almacenes, contact center y dependencia. Es el mismo equipo y la misma cobertura bajo los tres, así que al cambiar de convenio solo cambian las reglas.

## Arrancar

Hace falta Python 3.13 con [uv](https://docs.astral.sh/uv/) y Node 20.19 o 22.12 en adelante.

```bash
cd motor
uv run uvicorn motor.api:app --reload
```

```bash
cd web
npm install
npm run dev
```

La web queda en `http://localhost:5173` y pasa `/api` al motor en el puerto 8000. Con `?convenio=BOE-A-2023-13741` se abre directamente un convenio sin pasar por el diálogo de entrada.

El asistente usa qwen3:4b por [Ollama](https://ollama.com) (`ollama pull qwen3:4b`). Sin Ollama, todo lo demás funciona a mano.

Los cuadrantes de partida están guardados en `demo/cuadrantes/`. Si cambian la ficha de empresa o las reglas, se borran y el motor los regenera al pedirlos (hasta 60 s por convenio).

## Qué se puede hacer en la hoja

- **Ver el mes** por semana (cada celda dibuja el día de 0 a 24 h) o por día, con la cobertura debajo. El color es la clase de la hora: normal, nocturna, complementaria, extraordinaria, redistribución o ausencia.
- **Cambiar un turno** con doble clic o escribiendo sobre la celda (`7-15`, `tarde`, `22-6` para una noche, `libre`). Si rompe una regla, depende de lo que el convenio deje pactar:
  - si no se puede pactar, o es un mínimo del Estatuto, se bloquea con la cita;
  - si se puede pactar con la persona, se pide su acuerdo y queda registrado;
  - si solo se puede pactar con la representación, se bloquea mientras no haya un acuerdo colectivo;
  - un hueco de cobertura o una semana fuera de margen se avisa y se aplica, porque es política de la empresa y no ley.
- **Marcar una ausencia** con clic derecho. El solver la cubre moviendo lo mínimo, según el preaviso que haya, y cada hora añadida dice de qué clase es y de qué artículo sale.
- **Pedírselo al asistente** del panel derecho, con faltas incluidas: «carmen esta de baja asta el jueves», «pon a Marta de tarde el miércoles 11», «¿quién trabaja el sábado?». Hace lo mismo que la mano y por la misma vía, así que las reglas se aplican igual. Lo que no es del cuadrante no lo contesta.
- **Deshacer** cualquier cambio, hecho a mano o por el asistente (Ctrl+Z).

## Implantar un convenio nuevo

Leer el convenio es un paso de implantación, que se hace una vez y lo revisa una persona. La app nunca lee convenios.

1. **Bajar el texto del BOE.** Se usa el XML, que ya viene estructurado por artículos:

   ```bash
   cd motor
   uv run python -m motor.boe BOE-A-2023-13741
   ```

   Escribe `convenios/<BOE-ID>.md` con un `## Artículo N.` por artículo. Esa numeración es la que se cita.

2. **Pasarle el agente lector.** Desde la raíz del repo, con [Claude Code](https://claude.com/claude-code):

   ```bash
   claude -p "Lee el convenio BOE-A-2023-13741" --agent lector-convenio
   ```

   El agente (`.claude/agents/lector-convenio.md`) localiza los artículos de jornada, descansos, turnos y horas complementarias y escribe `reglas/<BOE-ID>.json`. Los tipos de regla son una lista cerrada con una opción `otra` para lo que no encaja. El agente es el mismo para cualquier convenio: lo que se revisa es su salida.

3. **Validar.** El agente ya lo hace, pero conviene repetirlo tras cualquier retoque a mano:

   ```bash
   cd motor
   uv run python -m motor.validar ../reglas/BOE-A-2023-13741.json
   ```

   Comprueba la forma de cada regla, que la cita esté literal en el artículo citado y que la cifra salga de la cita (en número, con punto de miles o en letra).

4. **Revisar a mano.** El validador garantiza que lo citado existe, pero no que la lectura sea correcta. Lo que más hay que mirar:
   - las reglas con `condicion`, porque el solver solo las aplica si la ficha de empresa dice que se cumple;
   - lo que es excepción y no condición (`excepto`);
   - el campo `pactable` y su `cita_pacto`, que deciden si una edición a mano se bloquea o pide acuerdo;
   - lo que ha quedado en `otra`, que el solver no aplica.

5. **Ficha de empresa.** `demo/empresa.json` describe el periodo, el horario de apertura, la gente que hace falta por hora, la plantilla con sus contratos y pactos, y los márgenes de la empresa sobre el contrato. En `condiciones`, bajo el identificador del convenio, van las condiciones que cumple la empresa, copiadas literalmente del campo `condicion` del JSON de reglas.

Lo que el convenio no regula lo pone el Estatuto de los Trabajadores desde el código (`motor/src/motor/reglas.py`), con su texto literal del BOE consolidado: 12 h entre jornadas, 9 h ordinarias al día, 40 h semanales de promedio, día y medio de descanso semanal y las reglas de complementarias y nocturnidad. Esos mínimos nunca son pactables.

## Cómo está hecho

```
motor/       Python + OR-Tools CP-SAT + FastAPI
  boe.py           XML del BOE a markdown por artículos
  reglas.py        esquema cerrado de reglas, mínimos del Estatuto y qué regla manda
  validar.py       cita literal y cifra dentro de la cita
  empresa.py       ficha de empresa y calendario del periodo
  solver.py        cada regla como restricción del modelo
  cumplimiento.py  comprobador independiente del solver; valida también las ediciones
  replanificar.py  ausencias con mínimo cambio y clase legal de cada hora añadida
  api.py           API local para la web
web/         React + Vite + TypeScript
reglas/      reglas revisadas de cada convenio, versionadas
convenios/   texto de cada convenio por artículos
demo/        ficha de empresa y cuadrantes de partida
```

Las decisiones las toma el solver. El comprobador cuenta los incumplimientos por su cuenta, sin compartir código con el solver, para que un error al traducir una regla a restricción salga a la vista.

Lo obligatorio es la jornada anual: cada semana puede desviarse del contrato dentro de un margen que fija la empresa, y la diferencia va al saldo de horas de cada persona.

El estado del proyecto y lo que queda pendiente está en [`docs/STATUS.md`](docs/STATUS.md).

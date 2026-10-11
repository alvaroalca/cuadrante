// Tipos y llamadas a la API del motor (motor/src/motor/api.py).

export type Turno = [number, number] // [inicio, fin] en horas; fin > 24 si cruza la medianoche
export type Cuadrante = Record<string, (Turno | null)[]>

export interface Cita {
  articulo: string
  texto: string
}

export interface Regla {
  tipo: string
  valor?: number
  valor_max?: number
  unidad?: string
  periodo?: string
  ventana_dias?: number
  turno?: string
  desde?: string
  hasta?: string
  condicion?: string
  excepto?: string
  vigente_desde?: number
  descripcion?: string
  pactable: 'individual' | 'colectivo' | 'no'
  cita: Cita
  cita_pacto?: Cita
  origen: 'convenio' | 'estatuto'
  estado?: string
}

export interface ConvenioResumen {
  boe: string
  nombre: string
  reglas: number
}

export interface Convenio {
  boe: string
  nombre: string
  completa: number
  efectivas: Regla[]
  resto: Regla[]
}

export interface Persona {
  nombre: string
  horas_semana: number | 'completa'
  indefinido: boolean
  pacto_complementarias_pct: number
  saldo_horas: number
  contrato: number
  objetivo: number
}

// Qué pasa con un cambio que provoca un incumplimiento (ver Incumplimiento.nivel en el motor).
export type Nivel = 'aviso' | 'acuerdo' | 'bloqueo'

export interface Incumplimiento {
  tipo: string
  mensaje: string
  persona: string | null
  dias: number[]
  regla: Regla | null
  nivel: Nivel
  pactado: boolean
}

/** Acuerdo individual registrado al confirmar un cambio: cubre justo esos incumplimientos. */
export interface Acuerdo {
  persona: string
  tipo: string
  dias: number[]
  mensaje: string
}

export interface Hoja {
  empresa: string
  fechas: string[]
  semanas: number[][]
  apertura: { desde: number; hasta: number }
  necesidad: number[][] // [día][hora]
  plantilla: Persona[]
  cuadrante: Cuadrante
  incumplimientos: Incumplimiento[]
}

export interface Ausencia {
  persona: string
  fecha: string
  desde?: number | null
  hasta?: number | null
  motivo: string
  aviso: string
  imprevista: boolean
}

/** Clase legal de una hora añadida al cubrir una ausencia. */
export type Clase = 'redistribucion' | 'voluntarias' | 'pactadas' | 'extras'

/** Todo lo que cambia con las acciones. Viaja entero al motor, que devuelve el nuevo. */
export interface Estado {
  boe: string
  cuadrante: Cuadrante
  ausencias: Ausencia[]
  acuerdos: Acuerdo[]
  clases: Record<string, Record<string, Clase>> // "persona|día" -> {hora: clase}
}

export interface RespuestaAccion {
  estado: Estado
  historial: Estado[]
  texto: string
  nivel?: Nivel | 'ok' | null
  ir_a?: string | null
  resaltar: [string, number][]
  incidencias?: Incumplimiento[]
  incumplimientos: Incumplimiento[]
}

/** Mensaje de la conversación con el modelo, tal como lo guarda Ollama. */
export interface MensajeModelo {
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string
  tool_calls?: unknown[]
  tool_name?: string
}

export type EventoAgente =
  | { tipo: 'accion'; nombre: string; args: Record<string, unknown>; texto: string; nivel: Nivel | 'ok' | null }
  | { tipo: 'fin'; respuesta: string; estado: Estado; historial: Estado[]; mensajes: MensajeModelo[]; resaltar: [string, number][]; ir_a: string | null; incumplimientos: Incumplimiento[] }
  | { tipo: 'error'; texto: string }

async function pedir<T>(ruta: string, cuerpo?: unknown): Promise<T> {
  const r = await fetch(`/api${ruta}`, cuerpo === undefined ? undefined : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cuerpo),
  })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

export const api = {
  convenios: () => pedir<ConvenioResumen[]>('/convenios'),
  convenio: (boe: string) => pedir<Convenio>(`/convenios/${boe}`),
  hoja: (boe: string) => pedir<Hoja>(`/cuadrante/${boe}`),
  accion: (estado: Estado, historial: Estado[], nombre: string, args: Record<string, unknown>, hoy: string) =>
    pedir<RespuestaAccion>('/accion', { estado, historial, nombre, args, hoy }),
  /** Va llamando a `alEvento` con cada paso del agente según llega. */
  async agente(estado: Estado, historial: Estado[], mensajes: MensajeModelo[], texto: string, hoy: string,
    alEvento: (e: EventoAgente) => void) {
    const r = await fetch('/api/agente', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ estado, historial, mensajes, texto, hoy }),
    })
    if (!r.ok || !r.body) throw new Error(`${r.status} ${await r.text()}`)
    const lector = r.body.pipeThrough(new TextDecoderStream()).getReader()
    let resto = ''
    for (;;) {
      const { value, done } = await lector.read()
      if (done) break
      resto += value
      const lineas = resto.split('\n')
      resto = lineas.pop()!
      for (const l of lineas) if (l.trim()) alEvento(JSON.parse(l))
    }
  },
}

/** "art. 23" o "ET 34.3": cómo se cita una regla en pantalla. */
export function articulo(r: Regla): string {
  return r.origen === 'estatuto' ? r.cita.articulo : `art. ${r.cita.articulo}`
}

// Tipos y llamadas a la API del motor (motor/src/motor/api.py).

export type Turno = [number, number] // [inicio, fin] en horas
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

export interface Incumplimiento {
  tipo: string
  mensaje: string
  persona: string | null
  dias: number[]
  regla: Regla | null
  nivel: Nivel
  pactado: boolean
}

// Qué hace una edición a mano que provoca un incumplimiento (ver Incumplimiento.nivel en el motor).
export type Nivel = 'aviso' | 'acuerdo' | 'bloqueo'

/** Acuerdo individual registrado al confirmar una edición: cubre justo esos incumplimientos. */
export interface Acuerdo {
  persona: string
  tipo: string
  dias: number[]
  mensaje: string
}

export interface Edicion {
  nivel: Nivel | 'ok'
  nuevos: Incumplimiento[]
  cuadrante: Cuadrante
  incumplimientos: Incumplimiento[]
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

export type Clase = 'redistribucion' | 'voluntarias' | 'pactadas' | 'extras'

export interface Cambio {
  persona: string
  dia: number
  antes: Turno | null
  despues: Turno
  horas: Partial<Record<Clase, number>>
}

export interface Opcion {
  clase: Clase
  puede: boolean
  motivo: string
  regla: Regla | null
}

export interface Replan {
  estado: string
  cuadrante: Cuadrante | null
  cambios: Cambio[]
  sin_cubrir: { dia: number; hora: number; faltan: number }[]
  opciones: Record<string, Opcion[]>
  incumplimientos: Incumplimiento[]
}

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
  editar: (boe: string, cuadrante: Cuadrante, persona: string, dia: number, turno: Turno | null, ausencias: Ausencia[], acuerdos: Acuerdo[]) =>
    pedir<Edicion>(`/editar/${boe}`, { cuadrante, persona, dia, turno, ausencias, acuerdos }),
  replanificar: (boe: string, cuadrante: Cuadrante, ausencias: Ausencia[], acuerdos: Acuerdo[]) =>
    pedir<Replan>(`/replanificar/${boe}`, { cuadrante, ausencias, acuerdos }),
}

export const NOMBRE_CLASE: Record<Clase, string> = {
  redistribucion: 'Redistribución',
  voluntarias: 'Complementarias voluntarias',
  pactadas: 'Complementarias pactadas',
  extras: 'Horas extraordinarias',
}

/** "art. 23" o "ET 34.3": cómo se cita una regla en pantalla. */
export function articulo(r: Regla): string {
  return r.origen === 'estatuto' ? r.cita.articulo : `art. ${r.cita.articulo}`
}

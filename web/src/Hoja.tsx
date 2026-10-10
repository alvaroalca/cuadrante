import type { MouseEvent } from 'react'
import type { Ausencia, Cambio, Cuadrante, Hoja as DatosHoja, Turno } from './api'

export type Fila = string | 'faltan' | 'hay'
export interface Seleccion { fila: Fila; col: number } // col: hora (vista día) o día (vista semana)

interface Props {
  hoja: DatosHoja
  cuadrante: Cuadrante
  ausencias: Ausencia[]
  cambios: Cambio[]
  editadas: Set<string> // `${persona}|${día}` editadas a mano
  seleccion: Seleccion | null
  onSeleccion: (s: Seleccion) => void
  onEditar: () => void
  onAusencia: (persona: string, dia: number) => void
  onNota: (e: MouseEvent, persona: string, dia: number) => void
  onSinNota: () => void
}

const LETRAS = Array.from({ length: 27 }, (_, i) => (i < 26 ? String.fromCharCode(65 + i) : 'AA'))
const HORAS = Array.from({ length: 24 }, (_, h) => h)

/** Noche si empieza de 21 a 5, mañana si antes de las 14 y tarde si no. Basta para pintar como un responsable. */
export const franja = (t: Turno) => (t[0] >= 21 || t[0] < 5 ? 'n' : t[0] < 14 ? 'm' : 't')
export const horas = (t: Turno | null) => (t ? t[1] - t[0] : 0)
const hh = (h: number) => String(h).padStart(2, '0')
/** Un turno que cruza la medianoche acaba al día siguiente: 22–06. */
export const fmt = (t: Turno) => `${hh(t[0])}–${hh(t[1] > 24 ? t[1] - 24 : t[1])}`
export const clave = (persona: string, dia: number) => `${persona}|${dia}`

function ausente(ausencias: Ausencia[], persona: string, fecha: string, h: number) {
  return ausencias.some(a => a.persona === persona && a.fecha === fecha
    && (a.desde == null || (a.desde <= h && h < (a.hasta ?? 24))))
}

function hayA(hoja: DatosHoja, c: Cuadrante, aus: Ausencia[], d: number, h: number) {
  return hoja.plantilla.filter(p => {
    const t = c[p.nombre][d]
    return t && t[0] <= h && h < t[1] && !ausente(aus, p.nombre, hoja.fechas[d], h)
  }).length
}

export function VistaDia({ dia, ...p }: Props & { dia: number }) {
  const { hoja, cuadrante, ausencias, cambios, seleccion } = p
  const fecha = hoja.fechas[dia]
  const abierta = (h: number) => h >= hoja.apertura.desde && h < hoja.apertura.hasta
  const sel = (fila: Fila, col: number) => seleccion?.fila === fila && seleccion.col === col
  const filaSel = seleccion?.fila
  const colSel = seleccion ? seleccion.col + 2 : -1

  return (
    <table className="rejilla">
      <thead>
        <tr>
          <th className="num" />
          {LETRAS.map((l, i) => <th key={l} className={i === colSel ? 'sel' : ''}>{l}</th>)}
        </tr>
      </thead>
      <tbody>
        <tr className="etiqueta" style={{ ['--i' as string]: 0 }}>
          <th className="num">1</th>
          <td className="nombre">Persona</td>
          <td className="contrato">h/sem</td>
          {HORAS.map(h => <td key={h} className={`hora ${abierta(h) ? '' : 'cerrado'}`}>{h}</td>)}
          <td className="total">Día</td>
        </tr>
        {hoja.plantilla.map((pers, i) => {
          const t = cuadrante[pers.nombre][dia]
          const ayer = dia > 0 ? cuadrante[pers.nombre][dia - 1] : null
          const sigue = ayer && ayer[1] > 24 ? ayer[1] - 24 : 0 // horas de la noche anterior que caen hoy
          const cambio = cambios.find(c => c.persona === pers.nombre && c.dia === dia)
          const editada = p.editadas.has(clave(pers.nombre, dia))
          return (
            <tr key={pers.nombre} style={{ ['--i' as string]: i + 1 }}>
              <th className={`num ${filaSel === pers.nombre ? 'sel' : ''}`}>{i + 2}</th>
              <td className="nombre">{pers.nombre}</td>
              <td className="contrato">{pers.contrato}</td>
              {HORAS.map(h => {
                const dentro = t && t[0] <= h && h < t[1]
                const aus = dentro && ausente(ausencias, pers.nombre, fecha, h)
                const nuevo = dentro && cambio && !(cambio.antes && cambio.antes[0] <= h && h < cambio.antes[1])
                const clases = ['hora']
                if (!abierta(h)) clases.push('cerrado')
                if (dentro) clases.push(aus ? 'aus' : nuevo ? 'nuevo' : franja(t!))
                else if (h < sigue) clases.push('n', 'sigue')
                if (dentro && h === t![0]) clases.push('ini')
                if (dentro && h === t![1] - 1) clases.push('fin')
                if ((cambio || editada) && dentro && h === t![0]) clases.push('comentado')
                if (sel(pers.nombre, h)) clases.push('activa')
                return (
                  <td
                    key={h}
                    className={clases.join(' ')}
                    onMouseDown={() => p.onSeleccion({ fila: pers.nombre, col: h })}
                    onDoubleClick={p.onEditar}
                    onContextMenu={e => { e.preventDefault(); p.onSeleccion({ fila: pers.nombre, col: h }); p.onAusencia(pers.nombre, dia) }}
                    onMouseEnter={(cambio || editada) && dentro ? e => p.onNota(e, pers.nombre, dia) : undefined}
                    onMouseLeave={(cambio || editada) && dentro ? p.onSinNota : undefined}
                  >
                    {aus && h === t![0] ? '×' : ''}
                    {nuevo && <span className={`hormigas ${h === cambio!.despues[0] ? 'ini' : ''} ${h === cambio!.despues[1] - 1 ? 'fin' : ''}`} />}
                  </td>
                )
              })}
              <td className="total">{horas(t) || ''}</td>
            </tr>
          )
        })}
        <tr className="hueco"><th className="num">{hoja.plantilla.length + 2}</th><td colSpan={27} /></tr>
        {(['faltan', 'hay'] as const).map((fila, j) => (
          <tr key={fila} className="cobertura" style={{ ['--i' as string]: hoja.plantilla.length + 2 + j }}>
            <th className={`num ${filaSel === fila ? 'sel' : ''}`}>{hoja.plantilla.length + 3 + j}</th>
            <td className="nombre">{fila === 'faltan' ? 'Hacen falta' : 'Hay'}</td>
            <td className="contrato" />
            {HORAS.map(h => {
              const necesidad = hoja.necesidad[dia][h]
              const hay = hayA(hoja, cuadrante, ausencias, dia, h)
              const valor = fila === 'faltan' ? necesidad : hay
              const formato = fila === 'hay' && necesidad ? (hay < necesidad ? 'corto' : 'justo') : ''
              return (
                <td key={h} className={`hora ${abierta(h) ? '' : 'cerrado'} ${formato} ${sel(fila, h) ? 'activa' : ''}`}
                  onMouseDown={() => p.onSeleccion({ fila, col: h })}>
                  {valor || ''}
                </td>
              )
            })}
            <td className="total" />
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function VistaSemana({ semana, ...p }: Props & { semana: number[] }) {
  const { hoja, cuadrante, ausencias, cambios, seleccion } = p
  const dias = 'LMXJVSD'
  return (
    <table className="rejilla">
      <thead>
        <tr>
          <th className="num" />
          {LETRAS.slice(0, semana.length + 3).map(l => <th key={l}>{l}</th>)}
        </tr>
      </thead>
      <tbody>
        <tr className="etiqueta">
          <th className="num">1</th>
          <td className="nombre">Persona</td>
          <td className="contrato">h/sem</td>
          {semana.map(d => {
            const f = new Date(hoja.fechas[d])
            return <td key={d} className="dia">{dias[(f.getDay() + 6) % 7]} {f.getDate()}</td>
          })}
          <td className="total">Semana</td>
        </tr>
        {hoja.plantilla.map((pers, i) => {
          const total = semana.reduce((s, d) => s + horas(cuadrante[pers.nombre][d]), 0)
          return (
            <tr key={pers.nombre} style={{ ['--i' as string]: i + 1 }}>
              <th className={`num ${seleccion?.fila === pers.nombre ? 'sel' : ''}`}>{i + 2}</th>
              <td className="nombre">{pers.nombre}</td>
              <td className="contrato">{pers.contrato}</td>
              {semana.map(d => {
                const t = cuadrante[pers.nombre][d]
                const cambio = cambios.find(c => c.persona === pers.nombre && c.dia === d)
                const editada = p.editadas.has(clave(pers.nombre, d))
                const aus = t && ausente(ausencias, pers.nombre, hoja.fechas[d], t[0])
                const clases = ['dia']
                if (t) clases.push(aus ? 'aus' : cambio ? 'nuevo' : franja(t))
                if (cambio || editada) clases.push('comentado')
                if (seleccion?.fila === pers.nombre && seleccion.col === d) clases.push('activa')
                return (
                  <td key={d} className={clases.join(' ')}
                    onMouseDown={() => p.onSeleccion({ fila: pers.nombre, col: d })}
                    onDoubleClick={p.onEditar}
                    onContextMenu={e => { e.preventDefault(); p.onSeleccion({ fila: pers.nombre, col: d }); p.onAusencia(pers.nombre, d) }}
                    onMouseEnter={cambio || editada ? e => p.onNota(e, pers.nombre, d) : undefined}
                    onMouseLeave={cambio || editada ? p.onSinNota : undefined}>
                    {t ? fmt(t) : ''}
                    {cambio && <span className="hormigas ini fin" />}
                  </td>
                )
              })}
              <td className="total">{total}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

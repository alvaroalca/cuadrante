import type { MouseEvent } from 'react'
import type { Estado, Hoja as DatosHoja, Turno } from './api'

export type ClaseHora = 'normal' | 'nocturna' | 'complementaria' | 'extra' | 'redistribucion' | 'ausencia'
export interface Seleccion { persona: string; dia: number }

export const DIAS = 'LMXJVSD'
export const NOMBRE_DIA = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
export const LEYENDA: [ClaseHora, string][] = [
  ['normal', 'Normal'], ['nocturna', 'Nocturna'], ['complementaria', 'Complementaria'],
  ['extra', 'Extraordinaria'], ['redistribucion', 'Redistribución'], ['ausencia', 'Ausencia'],
]

export const horas = (t: Turno | null) => (t ? t[1] - t[0] : 0)
const hh = (h: number) => String(h).padStart(2, '0')
/** Un turno que cruza la medianoche acaba al día siguiente: 22–06. */
export const fmt = (t: Turno) => `${hh(t[0])}–${hh(t[1] > 24 ? t[1] - 24 : t[1])}`
export const clave = (persona: string, dia: number) => `${persona}|${dia}`
export const diaSemana = (fecha: string) => (new Date(fecha).getDay() + 6) % 7

function ausente(e: Estado, persona: string, fecha: string, h: number) {
  return e.ausencias.some(a => a.persona === persona && a.fecha === fecha
    && (a.desde == null || (a.desde <= h && h < (a.hasta ?? 24))))
}

/** Clase de la hora h (puede pasar de 24 si el turno cruza la medianoche) del turno de la persona el día d. */
export function claseHora(hoja: DatosHoja, e: Estado, persona: string, d: number, h: number): ClaseHora {
  if (h < 24 && ausente(e, persona, hoja.fechas[d], h)) return 'ausencia'
  const c = e.clases[clave(persona, d)]?.[String(h)]
  if (c === 'voluntarias' || c === 'pactadas') return 'complementaria'
  if (c === 'extras') return 'extra'
  if (c === 'redistribucion') return 'redistribucion'
  const r = h % 24
  return r >= 22 || r < 6 ? 'nocturna' : 'normal'
}

/** Horas que se pintan el día d, de 0 a 24: su turno y lo que la noche de ayer trae a hoy. */
function horasDelDia(hoja: DatosHoja, e: Estado, persona: string, d: number): { h: number; c: ClaseHora }[] {
  const out: { h: number; c: ClaseHora }[] = []
  const ayer = d > 0 ? e.cuadrante[persona][d - 1] : null
  if (ayer && ayer[1] > 24) for (let h = 24; h < ayer[1]; h++) out.push({ h: h - 24, c: claseHora(hoja, e, persona, d - 1, h) })
  const t = e.cuadrante[persona][d]
  if (t) for (let h = t[0]; h < Math.min(t[1], 24); h++) out.push({ h, c: claseHora(hoja, e, persona, d, h) })
  return out
}

/** Tramos seguidos de la misma clase, para pintarlos como un bloque. */
function tramos(hs: { h: number; c: ClaseHora }[]) {
  const out: { desde: number; hasta: number; c: ClaseHora }[] = []
  for (const { h, c } of hs) {
    const u = out[out.length - 1]
    if (u && u.hasta === h && u.c === c) u.hasta++
    else out.push({ desde: h, hasta: h + 1, c })
  }
  return out
}

function hayA(hoja: DatosHoja, e: Estado, d: number, h: number) {
  return hoja.plantilla.filter(p => horasDelDia(hoja, e, p.nombre, d).some(x => x.h === h && x.c !== 'ausencia')).length
}

interface Props {
  hoja: DatosHoja
  estado: Estado
  hoy: number
  seleccion: Seleccion | null
  resaltar: Set<string>
  pactadas: Set<string>
  onSeleccion: (s: Seleccion) => void
  onEditar: (s: Seleccion, e: MouseEvent) => void
  onMenu: (s: Seleccion, e: MouseEvent) => void
}

function Persona({ nombre, contrato, sub, celda }: { nombre: string; contrato: number; sub?: string; celda?: string }) {
  return <th className="persona" data-celda={celda}><b>{nombre}</b><small>{contrato} h/sem{sub ? ` · ${sub}` : ''}</small></th>
}

export function VistaSemana({ semana, ...p }: Props & { semana: number[] }) {
  const { hoja, estado } = p
  return (
    <table className="rejilla">
      <thead>
        <tr>
          <th className="persona">Persona</th>
          {semana.map(d => {
            const f = new Date(hoja.fechas[d])
            const ds = diaSemana(hoja.fechas[d])
            return <th key={d} className={`${d === p.hoy ? 'hoy' : ''} ${ds >= 5 ? 'finde' : ''}`}>{NOMBRE_DIA[ds]} {f.getDate()}{d === p.hoy ? ' · hoy' : ''}</th>
          })}
          <th className="total">Semana</th>
        </tr>
      </thead>
      <tbody>
        {hoja.plantilla.map(pers => {
          const total = semana.reduce((s, d) => s + horas(estado.cuadrante[pers.nombre][d]), 0)
          return (
            <tr key={pers.nombre}>
              <Persona nombre={pers.nombre} contrato={pers.contrato} />
              {semana.map(d => {
                const t = estado.cuadrante[pers.nombre][d]
                const s = { persona: pers.nombre, dia: d }
                const k = clave(pers.nombre, d)
                const aus = t && ausente(estado, pers.nombre, hoja.fechas[d], t[0])
                const cls = ['celda']
                if (p.seleccion?.persona === pers.nombre && p.seleccion.dia === d) cls.push('sel')
                if (p.resaltar.has(k)) cls.push('resaltada')
                if (p.pactadas.has(k)) cls.push('pactada')
                return (
                  <td key={d} className={cls.join(' ')} tabIndex={-1} data-celda={k}
                    onMouseDown={() => p.onSeleccion(s)}
                    onDoubleClick={e => p.onEditar(s, e)}
                    onContextMenu={e => { e.preventDefault(); p.onSeleccion(s); p.onMenu(s, e) }}>
                    <div className={`texto ${t ? '' : 'libre'}`}>{t ? fmt(t) : 'libre'}{aus ? ' · ausente' : ''}</div>
                    <div className="linea24" aria-hidden>
                      {tramos(horasDelDia(hoja, estado, pers.nombre, d)).map(x => (
                        <i key={x.desde} className={`c-${x.c}`} style={{ left: `${x.desde / 24 * 100}%`, width: `${(x.hasta - x.desde) / 24 * 100}%` }} />
                      ))}
                    </div>
                  </td>
                )
              })}
              <td className="total">{total} h</td>
            </tr>
          )
        })}
        <tr className="cobertura">
          <th className="persona">Cobertura</th>
          {semana.map(d => {
            const falta = Array.from({ length: 24 }, (_, h) => Math.max(0, hoja.necesidad[d][h] - hayA(hoja, estado, d, h))).reduce((a, b) => a + b, 0)
            return <td key={d} className={falta ? 'corto' : ''}>{falta ? `faltan ${falta} h` : 'cubierta'}</td>
          })}
          <td />
        </tr>
      </tbody>
    </table>
  )
}

export function VistaDia({ dia, ...p }: Props & { dia: number }) {
  const { hoja, estado } = p
  return (
    <table className="rejilla">
      <thead>
        <tr>
          <th className="persona">Persona</th>
          {Array.from({ length: 24 }, (_, h) => <th key={h} className="hora">{h}</th>)}
          <th className="total">Día</th>
        </tr>
      </thead>
      <tbody>
        {hoja.plantilla.map(pers => {
          const t = estado.cuadrante[pers.nombre][dia]
          const s = { persona: pers.nombre, dia }
          const sel = p.seleccion?.persona === pers.nombre && p.seleccion.dia === dia
          const res = p.resaltar.has(clave(pers.nombre, dia))
          const hs = horasDelDia(hoja, estado, pers.nombre, dia)
          return (
            <tr key={pers.nombre}>
              <Persona nombre={pers.nombre} contrato={pers.contrato} sub={t ? fmt(t) : 'libre'} celda={clave(pers.nombre, dia)} />
              <td colSpan={24} className={`pista ${sel ? 'sel' : ''}`}
                style={{ ['--abre' as string]: hoja.apertura.desde, ['--cierra' as string]: hoja.apertura.hasta }}
                onMouseDown={() => p.onSeleccion(s)}
                onDoubleClick={e => p.onEditar(s, e)}
                onContextMenu={e => { e.preventDefault(); p.onSeleccion(s); p.onMenu(s, e) }}>
                {tramos(hs).map(x => (
                  <i key={x.desde} className={`c-${x.c}`} style={{ left: `${x.desde / 24 * 100}%`, width: `${(x.hasta - x.desde) / 24 * 100}%` }} />
                ))}
                {res && hs.length > 0 && (
                  <b className="marco" style={{ left: `${hs[0].h / 24 * 100}%`, width: `${(hs[hs.length - 1].h + 1 - hs[0].h) / 24 * 100}%` }} />
                )}
              </td>
              <td className="total">{horas(t) || ''}</td>
            </tr>
          )
        })}
        <tr className="cobertura">
          <th className="persona">Hay / hacen falta</th>
          {Array.from({ length: 24 }, (_, h) => {
            const nec = hoja.necesidad[dia][h]
            const hay = hayA(hoja, estado, dia, h)
            return <td key={h} className={`hora ${nec && hay < nec ? 'corto' : ''}`}>{nec ? `${hay}/${nec}` : ''}</td>
          })}
          <td />
        </tr>
      </tbody>
    </table>
  )
}

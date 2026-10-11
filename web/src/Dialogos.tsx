import { useState } from 'react'
import type { ReactNode } from 'react'
import { articulo } from './api'
import type { ConvenioResumen, Hoja, Incumplimiento, Nivel } from './api'
import { DIAS, diaSemana } from './Hoja'

function Dialogo({ titulo, icono, children, pie, onCerrar }: { titulo: string; icono?: ReactNode; children: ReactNode; pie: ReactNode; onCerrar?: () => void }) {
  return (
    <div className="velo" onMouseDown={e => e.target === e.currentTarget && onCerrar?.()}
      onKeyDown={e => e.key === 'Escape' && onCerrar?.()}>
      <div className="dialogo" role="dialog" aria-label={titulo}>
        <header>{icono}{titulo}</header>
        <div className="cuerpo">{children}</div>
        <footer>{pie}</footer>
      </div>
    </div>
  )
}

export function DialogoConvenio({ convenios, actual, onElegir, onCerrar }: {
  convenios: ConvenioResumen[]
  actual: string | null
  onElegir: (boe: string) => void
  onCerrar?: () => void
}) {
  const [elegido, setElegido] = useState(actual ?? convenios[0]?.boe)
  return (
    <Dialogo titulo="¿Bajo qué convenio trabaja el equipo?" onCerrar={onCerrar}
      pie={<>
        {onCerrar && <button className="boton" onClick={onCerrar}>Cancelar</button>}
        <button className="boton principal" disabled={!elegido} onClick={() => onElegir(elegido!)}>Abrir el cuadrante</button>
      </>}>
      <p className="apagado" style={{ margin: 0 }}>El cuadrante aplica sus reglas, y lo que el convenio no regula lo pone el Estatuto de los Trabajadores.</p>
      <div className="convenios">
        {convenios.map(c => (
          <button key={c.boe} aria-pressed={c.boe === elegido} onClick={() => setElegido(c.boe)} onDoubleClick={() => onElegir(c.boe)}>
            <b>{c.nombre}</b>
            <span className="art">{c.boe} · {c.reglas} reglas</span>
          </button>
        ))}
      </div>
    </Dialogo>
  )
}

const MOTIVOS = ['baja', 'cita médica', 'examen', 'asunto propio', 'vacaciones', 'otro']

/** Argumentos de la acción marcar_ausencia, con las fechas en ISO. */
export interface DatosAusencia {
  persona: string; dia: string; hasta_dia: string; horas?: string; motivo: string; aviso: string; imprevista: boolean
}

export function DialogoAusencia({ hoja, persona, dia, hoy, onAceptar, onCerrar }: {
  hoja: Hoja
  persona: string
  dia: number
  hoy: string
  onAceptar: (a: DatosAusencia) => void
  onCerrar: () => void
}) {
  const [quien, setQuien] = useState(persona)
  const [d, setD] = useState(dia)
  const [d2, setD2] = useState(dia)
  const turno = hoja.cuadrante[quien]?.[d] ?? null
  const [entero, setEntero] = useState(true)
  const [desde, setDesde] = useState(turno?.[0] ?? 9)
  const [hasta, setHasta] = useState(turno ? Math.min(turno[0] + 2, turno[1]) : 11)
  const [motivo, setMotivo] = useState('baja')
  const [aviso, setAviso] = useState(hoy <= hoja.fechas[dia] ? hoy : hoja.fechas[dia])
  const etiqueta = (i: number) => `${DIAS[diaSemana(hoja.fechas[i])]} ${new Date(hoja.fechas[i]).getDate()}/${new Date(hoja.fechas[i]).getMonth() + 1}`
  const valido = entero || desde < hasta

  return (
    <Dialogo titulo="Marcar ausencia" onCerrar={onCerrar}
      pie={<>
        <button className="boton" onClick={onCerrar}>Cancelar</button>
        <button className="boton principal" disabled={!valido} onClick={() => onAceptar({
          persona: quien, dia: hoja.fechas[d], hasta_dia: hoja.fechas[d2], motivo, aviso,
          imprevista: motivo !== 'vacaciones', ...(entero ? {} : { horas: `${desde}-${hasta}` }),
        })}>Marcar y cubrir</button>
      </>}>
      <div className="fila">
        <label className="campo"><span>Quién</span>
          <select value={quien} onChange={e => setQuien(e.target.value)}>
            {hoja.plantilla.map(p => <option key={p.nombre}>{p.nombre}</option>)}
          </select>
        </label>
        <label className="campo"><span>Motivo</span>
          <select value={motivo} onChange={e => setMotivo(e.target.value)}>
            {MOTIVOS.map(m => <option key={m}>{m}</option>)}
          </select>
        </label>
      </div>
      <div className="fila">
        <label className="campo"><span>Desde</span>
          <select value={d} onChange={e => { const v = Number(e.target.value); setD(v); setD2(Math.max(d2, v)) }}>
            {hoja.fechas.map((_, i) => <option key={i} value={i}>{etiqueta(i)}</option>)}
          </select>
        </label>
        <label className="campo"><span>Hasta</span>
          <select value={d2} onChange={e => setD2(Number(e.target.value))}>
            {hoja.fechas.map((_, i) => i >= d && <option key={i} value={i}>{etiqueta(i)}</option>)}
          </select>
        </label>
      </div>
      <div className="fila">
        <div className="segmentado">
          <button aria-pressed={entero} onClick={() => setEntero(true)}>Todo el día</button>
          <button aria-pressed={!entero} onClick={() => setEntero(false)}>Unas horas</button>
        </div>
        {!entero && <>
          <input className="cifra" style={{ width: 56 }} type="number" min={0} max={23} value={desde} onChange={e => setDesde(Number(e.target.value))} aria-label="Desde la hora" />
          a
          <input className="cifra" style={{ width: 56 }} type="number" min={1} max={24} value={hasta} onChange={e => setHasta(Number(e.target.value))} aria-label="Hasta la hora" />
        </>}
      </div>
      <label className="campo"><span>La empresa se entera el</span>
        <input type="date" value={aviso} max={hoja.fechas[d]} onChange={e => setAviso(e.target.value)} />
      </label>
      <p className="apagado" style={{ margin: 0, fontSize: 12 }}>
        {d2 > d ? `${d2 - d + 1} días seguidos. ` : turno ? `Ese día tiene turno de ${turno[0]} a ${turno[1]}. ` : 'Ese día libra. '}
        El preaviso decide qué horas se pueden pedir: la redistribución y las complementarias pactadas piden días de antelación.
      </p>
    </Dialogo>
  )
}

const ORDEN: Nivel[] = ['bloqueo', 'acuerdo', 'aviso']

/** Un incumplimiento por regla y persona: un cambio puede romper muchas ventanas de la misma regla. */
function agrupar(nuevos: Incumplimiento[]) {
  const grupos = new Map<string, { i: Incumplimiento; n: number }>()
  for (const i of nuevos) {
    const k = `${i.nivel}|${i.tipo}|${i.persona}`
    const g = grupos.get(k)
    if (g) g.n++
    else grupos.set(k, { i, n: 1 })
  }
  return [...grupos.values()].sort((a, b) => ORDEN.indexOf(a.i.nivel) - ORDEN.indexOf(b.i.nivel))
}

function Incidencia({ i, n = 1 }: { i: Incumplimiento; n?: number }) {
  const r = i.regla
  return (
    <div className={`incidencia ${i.nivel}`}>
      <span>{i.mensaje}{n > 1 ? ` (y ${n - 1} más)` : ''} {r && <span className="art">{articulo(r)}</span>}</span>
      {r && <q>{r.cita.texto}</q>}
      {i.nivel === 'bloqueo' && r && <span className="apagado" style={{ fontSize: 12 }}>{r.origen === 'estatuto'
        ? 'Mínimo del Estatuto: no se puede pactar (ET 3.5).'
        : r.pactable === 'colectivo' ? 'Solo con un acuerdo colectivo, y no hay ninguno cargado.' : 'El convenio no deja pactarlo.'}</span>}
      {i.nivel === 'acuerdo' && r?.cita_pacto && (
        <span className="apagado" style={{ fontSize: 12 }}>Se puede pactar con la persona: <q>{r.cita_pacto.texto}</q> <span className="art">{articulo({ ...r, cita: r.cita_pacto })}</span></span>
      )}
    </div>
  )
}

/** Un cambio a mano que el convenio bloquea o que necesita el acuerdo de la persona. */
export function DialogoNivel({ nivel, que, persona, incidencias, onAcordar, onCerrar }: {
  nivel: 'bloqueo' | 'acuerdo'
  que: string
  persona: string
  incidencias: Incumplimiento[]
  onAcordar: () => void
  onCerrar: () => void
}) {
  return (
    <Dialogo titulo={nivel === 'bloqueo' ? 'El convenio no lo permite' : `Hace falta el acuerdo de ${persona}`}
      icono={<span className={`icono-nivel ${nivel}`}>{nivel === 'bloqueo' ? '×' : '!'}</span>}
      onCerrar={onCerrar}
      pie={nivel === 'bloqueo'
        ? <button className="boton principal" onClick={onCerrar}>Entendido</button>
        : <>
          <button className="boton" onClick={onCerrar}>Cancelar</button>
          <button className="boton principal" onClick={onAcordar}>{persona} está de acuerdo</button>
        </>}>
      <b>{que}</b>
      <span className="apagado">{nivel === 'bloqueo'
        ? 'Rompe una regla que no se puede pactar con la persona. El cuadrante se queda como estaba.'
        : `Rompe una regla que el convenio deja pactar con la persona. Si ${persona} está de acuerdo, se aplica y el acuerdo queda registrado.`}</span>
      {agrupar(incidencias).map(({ i, n }) => <Incidencia key={`${i.nivel}|${i.tipo}|${i.persona}`} i={i} n={n} />)}
    </Dialogo>
  )
}

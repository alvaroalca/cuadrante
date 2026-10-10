import { useState } from 'react'
import type { ReactNode } from 'react'
import { articulo } from './api'
import type { Ausencia, ConvenioResumen, Edicion, Hoja, Incumplimiento, Nivel, Turno } from './api'
import { fmt } from './Hoja'

function Dialogo({ titulo, children, pie, onCerrar }: { titulo: string; children: ReactNode; pie: ReactNode; onCerrar?: () => void }) {
  return (
    <div className="velo" onMouseDown={e => e.target === e.currentTarget && onCerrar?.()}>
      <div className="dialogo" role="dialog" aria-label={titulo}>
        <div className="titulo">
          <span>{titulo}</span>
          {onCerrar && <button className="boton" style={{ marginLeft: 'auto', minWidth: 0, padding: '0 5px', lineHeight: '14px' }} onClick={onCerrar} aria-label="Cerrar">×</button>}
        </div>
        <div className="cuerpo">{children}</div>
        <div className="pie">{pie}</div>
      </div>
    </div>
  )
}

// Cada plantilla se pinta como una hojita con franjas del color de sus turnos.
const FRANJAS: Record<string, string[]> = {
  'BOE-A-2023-13740': ['#ffff99', '#ffff99', '#99ccff', '#ffff99', '#99ccff'],
  'BOE-A-2023-13741': ['#99ccff', '#ffff99', '#99ccff', '#99ccff', '#ffff99'],
  'BOE-A-2023-13742': ['#ffff99', '#99ccff', '#ff99cc', '#ffff99', '#99ccff'],
}

export function DialogoConvenio({ convenios, actual, onElegir, onCerrar }: {
  convenios: ConvenioResumen[]
  actual: string | null
  onElegir: (boe: string) => void
  onCerrar?: () => void
}) {
  const [elegido, setElegido] = useState(actual ?? convenios[0]?.boe)
  return (
    <Dialogo
      titulo="Nuevo cuadrante"
      onCerrar={onCerrar}
      pie={<>
        {onCerrar && <button className="boton" onClick={onCerrar}>Cancelar</button>}
        <button className="boton principal" disabled={!elegido} onClick={() => onElegir(elegido!)}>Aceptar</button>
      </>}
    >
      <p style={{ margin: 0 }}>¿Bajo qué convenio trabaja la plantilla? La hoja aplica sus reglas, y lo que el convenio no regula lo pone el Estatuto.</p>
      <fieldset>
        <legend>Convenios colectivos</legend>
        <div className="plantillas">
          {convenios.map(c => (
            <button key={c.boe} className="plantilla" aria-pressed={c.boe === elegido}
              onClick={() => setElegido(c.boe)} onDoubleClick={() => onElegir(c.boe)}>
              <span className="hojita">
                {(FRANJAS[c.boe] ?? []).map((color, i) => (
                  <span key={i} style={{ background: color, top: 9 * (i + 1) + 1, left: 16 * (i % 3) + 1, width: 16 * (1 + (i % 2)) - 1 }} />
                ))}
              </span>
              <span className="rotulo">{c.nombre}</span>
              <span className="boe">{c.boe} · {c.reglas} reglas</span>
            </button>
          ))}
        </div>
      </fieldset>
    </Dialogo>
  )
}

const MOTIVOS = ['baja', 'cita médica', 'examen', 'asunto propio', 'otro']

export function DialogoAusencia({ hoja, persona, dia, onAceptar, onCerrar }: {
  hoja: Hoja
  persona: string
  dia: number
  onAceptar: (a: Ausencia) => void
  onCerrar: () => void
}) {
  const [quien, setQuien] = useState(persona)
  const [d, setD] = useState(dia)
  const turno = hoja.cuadrante[quien]?.[d] ?? null
  const [entero, setEntero] = useState(true)
  const [desde, setDesde] = useState(turno?.[0] ?? 9)
  const [hasta, setHasta] = useState(turno ? Math.min(turno[0] + 2, turno[1]) : 11)
  const [motivo, setMotivo] = useState('baja')
  const fecha = hoja.fechas[d]
  const ayer = new Date(new Date(fecha).getTime() - 86400000).toISOString().slice(0, 10)
  const [aviso, setAviso] = useState(ayer)
  const [imprevista, setImprevista] = useState(true)
  const dias = 'LMXJVSD'
  const etiqueta = (i: number) => {
    const f = new Date(hoja.fechas[i])
    return `${dias[(f.getDay() + 6) % 7]} ${f.getDate()}/${f.getMonth() + 1}`
  }
  const valido = entero || desde < hasta

  return (
    <Dialogo
      titulo="Insertar ausencia"
      onCerrar={onCerrar}
      pie={<>
        <button className="boton" onClick={onCerrar}>Cancelar</button>
        <button className="boton principal" disabled={!valido} onClick={() => onAceptar({
          persona: quien, fecha, motivo, aviso, imprevista,
          desde: entero ? null : desde, hasta: entero ? null : hasta,
        })}>Aceptar</button>
      </>}
    >
      <fieldset>
        <legend>Quién y cuándo</legend>
        <div className="fila">
          <select value={quien} onChange={e => setQuien(e.target.value)}>
            {hoja.plantilla.map(p => <option key={p.nombre}>{p.nombre}</option>)}
          </select>
          <select value={d} onChange={e => setD(Number(e.target.value))}>
            {hoja.fechas.map((_, i) => <option key={i} value={i}>{etiqueta(i)}</option>)}
          </select>
          <select value={motivo} onChange={e => setMotivo(e.target.value)}>
            {MOTIVOS.map(m => <option key={m}>{m}</option>)}
          </select>
        </div>
        <p className="apagado" style={{ margin: '8px 0 0' }}>
          Ese día tiene {turno ? `turno de ${turno[0]} a ${turno[1]}` : 'libre: la ausencia no deja ningún hueco'}.
        </p>
      </fieldset>
      <fieldset>
        <legend>Horas</legend>
        <div className="fila">
          <label><input type="radio" checked={entero} onChange={() => setEntero(true)} /> Todo el día</label>
          <label><input type="radio" checked={!entero} onChange={() => setEntero(false)} /> De</label>
          <input type="number" min={0} max={23} value={desde} disabled={entero} onChange={e => setDesde(Number(e.target.value))} />
          a
          <input type="number" min={1} max={24} value={hasta} disabled={entero} onChange={e => setHasta(Number(e.target.value))} />
        </div>
      </fieldset>
      <fieldset>
        <legend>Aviso</legend>
        <div className="fila">
          <label>La empresa se entera el <input type="date" value={aviso} max={fecha} onChange={e => setAviso(e.target.value)} /></label>
          <label><input type="checkbox" checked={imprevista} onChange={e => setImprevista(e.target.checked)} /> Imprevista</label>
        </div>
        <p className="apagado" style={{ margin: '8px 0 0' }}>El preaviso decide qué horas se pueden pedir: las complementarias pactadas y la redistribución piden días de antelación.</p>
      </fieldset>
    </Dialogo>
  )
}

// Iconos de mensaje de la época: alto, advertencia, información.
function IconoMensaje({ nivel }: { nivel: Nivel }) {
  if (nivel === 'bloqueo') return (
    <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden>
      <circle cx="16" cy="16" r="14" fill="#e00000" stroke="#800000" />
      <path d="M10 10l12 12M22 10L10 22" stroke="#fff" strokeWidth="3.5" />
    </svg>
  )
  if (nivel === 'acuerdo') return (
    <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden>
      <path d="M16 2L31 29H1z" fill="#ffff00" stroke="#000" />
      <path d="M16 11v9" stroke="#000" strokeWidth="3.5" /><circle cx="16" cy="24.5" r="2" />
    </svg>
  )
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden>
      <circle cx="16" cy="16" r="14" fill="#fff" stroke="#0a246a" />
      <circle cx="16" cy="9" r="2.2" fill="#0a246a" /><path d="M16 13v11" stroke="#0a246a" strokeWidth="3.5" />
    </svg>
  )
}

const ORDEN: Nivel[] = ['bloqueo', 'acuerdo', 'aviso']

/** Un incumplimiento por regla y persona: una edición puede romper muchas ventanas de la misma regla. */
export function agrupar(nuevos: Incumplimiento[]) {
  const grupos = new Map<string, { i: Incumplimiento; n: number }>()
  for (const i of nuevos) {
    const k = `${i.nivel}|${i.tipo}|${i.persona}`
    const g = grupos.get(k)
    if (g) g.n++
    else grupos.set(k, { i, n: 1 })
  }
  return [...grupos.values()].sort((a, b) => ORDEN.indexOf(a.i.nivel) - ORDEN.indexOf(b.i.nivel))
}

export function Incidencia({ i, n = 1 }: { i: Incumplimiento; n?: number }) {
  const r = i.regla
  return (
    <div className={`incidencia ${i.nivel}`}>
      <span>
        {i.mensaje}{n > 1 ? ` (y ${n - 1} más)` : ''}
        {r && <> <span className="art">{articulo(r)}</span></>}
      </span>
      {r && <q>{r.cita.texto}</q>}
      {i.nivel === 'bloqueo' && r && (r.origen === 'estatuto'
        ? <span className="apagado">Mínimo del Estatuto: no se puede pactar (ET 3.5).</span>
        : r.pactable === 'colectivo'
          ? <span className="apagado">Solo con acuerdo colectivo, y no hay ninguno cargado. <q>{r.cita_pacto!.texto}</q> <span className="art">{articulo({ ...r, cita: r.cita_pacto! })}</span></span>
          : <span className="apagado">El convenio no deja pactarlo.</span>)}
      {i.nivel === 'acuerdo' && r?.cita_pacto && (
        <span className="apagado">Se puede pactar con la persona: <q>{r.cita_pacto.texto}</q> <span className="art">{articulo({ ...r, cita: r.cita_pacto })}</span></span>
      )}
      {i.nivel === 'aviso' && <span className="apagado">{i.tipo === 'cobertura' ? 'Necesidad de la empresa, no ley: se avisa y se aplica.' : 'Margen de la empresa sobre el contrato; la diferencia va al saldo anual.'}</span>}
    </div>
  )
}

export function DialogoEdicion({ persona, dia, antes, despues, edicion, onAcordar, onCerrar }: {
  persona: string
  dia: string
  antes: Turno | null
  despues: Turno | null
  edicion: Edicion
  onAcordar: () => void
  onCerrar: () => void
}) {
  const nivel = edicion.nivel as Nivel
  const cambio = `${persona}, ${dia}: ${antes ? fmt(antes) : 'libre'} → ${despues ? fmt(despues) : 'libre'}`
  return (
    <Dialogo
      titulo={nivel === 'bloqueo' ? 'No se puede aplicar' : 'Hace falta acuerdo'}
      onCerrar={onCerrar}
      pie={nivel === 'bloqueo'
        ? <button className="boton principal" onClick={onCerrar}>Aceptar</button>
        : <>
          <button className="boton" onClick={onCerrar}>Cancelar</button>
          <button className="boton principal" onClick={onAcordar}>Hay acuerdo con {persona}</button>
        </>}
    >
      <div className="mensaje">
        <IconoMensaje nivel={nivel} />
        <div style={{ display: 'grid', gap: 8 }}>
          <b>{cambio}</b>
          <span>{nivel === 'bloqueo'
            ? 'La edición rompe una regla que no se puede pactar con la persona. El cuadrante se queda como estaba.'
            : `Rompe una regla que el convenio deja pactar con la persona. Si ${persona} está de acuerdo, se aplica y el acuerdo queda registrado.`}</span>
          {agrupar(edicion.nuevos).map(({ i, n }) => <Incidencia key={`${i.nivel}|${i.tipo}|${i.persona}`} i={i} n={n} />)}
        </div>
      </div>
    </Dialogo>
  )
}

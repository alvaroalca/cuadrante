import { useState } from 'react'
import type { ReactNode } from 'react'
import type { Ausencia, ConvenioResumen, Hoja } from './api'

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

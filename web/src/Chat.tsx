import { useEffect, useRef, useState } from 'react'
import type { Nivel } from './api'

export type Item =
  | { tipo: 'usuario' | 'asistente' | 'error'; texto: string }
  | { tipo: 'paso'; nombre: string; texto: string; nivel: Nivel | 'ok' | null }

const ACCION: Record<string, string> = {
  ver_cuadrante: 'Mirar el cuadrante',
  ver_horas: 'Mirar horas',
  ver_incumplimientos: 'Revisar el cuadrante',
  explicar_regla: 'Buscar en el convenio',
  marcar_ausencia: 'Marcar ausencia y cubrirla',
  cambiar_turno: 'Cambiar turno',
  intercambiar_turnos: 'Intercambiar turnos',
  deshacer: 'Deshacer',
  ir_a: 'Ir a',
  cambiar_convenio: 'Cambiar de convenio',
}
const CONSULTA = new Set(['ver_cuadrante', 'ver_horas', 'ver_incumplimientos', 'explicar_regla', 'ir_a'])

const SUGERENCIAS = [
  'Carmen está de baja hasta el jueves',
  '¿Quién trabaja el sábado?',
  'Pon a Marta de tarde el jueves',
  '¿Hay algún problema en el cuadrante?',
]

export function Chat({ items, pensando, onEnviar, onCerrar }: {
  items: Item[]
  pensando: boolean
  onEnviar: (texto: string) => void
  onCerrar: () => void
}) {
  const [texto, setTexto] = useState('')
  const hilo = useRef<HTMLDivElement>(null)
  useEffect(() => { hilo.current?.scrollTo({ top: hilo.current.scrollHeight, behavior: 'smooth' }) }, [items, pensando])

  function enviar(t = texto) {
    if (!t.trim() || pensando) return
    onEnviar(t.trim())
    setTexto('')
  }

  return (
    <aside className="chat">
      <header>
        Asistente <span className="apagado">qwen3.5:4b en local</span>
        <button className="boton" style={{ marginLeft: 'auto', padding: '2px 8px' }} onClick={onCerrar} aria-label="Cerrar el asistente">×</button>
      </header>
      <div className="hilo" ref={hilo}>
        {items.length === 0 && (
          <>
            <p className="apagado" style={{ margin: 0 }}>
              Pídeme lo que harías a mano: marcar ausencias, mover turnos, revisar el cuadrante o preguntar qué dice el convenio.
              Todo lo que cambio se puede deshacer.
            </p>
            <div className="sugerencias">
              {SUGERENCIAS.map(s => <button key={s} onClick={() => enviar(s)}>{s}</button>)}
            </div>
          </>
        )}
        {items.map((it, i) => it.tipo === 'paso'
          ? (
            <div key={i} className={`paso ${it.nivel === 'bloqueo' || it.nivel === 'acuerdo' ? it.nivel : CONSULTA.has(it.nombre) ? 'consulta' : ''}`}>
              <span className="bola" />
              <span>{ACCION[it.nombre] ?? it.nombre}{it.nivel === 'bloqueo' ? ': el convenio no lo permite' : it.nivel === 'acuerdo' ? ': hace falta acuerdo' : ''}</span>
            </div>
          )
          : <div key={i} className={`burbuja ${it.tipo}`}>{it.texto}</div>)}
        {pensando && <div className="pensando" aria-label="Pensando"><i /><i /><i /></div>}
      </div>
      <div className="entrada">
        <textarea value={texto} placeholder="Escribe lo que necesitas…" aria-label="Mensaje para el asistente"
          onChange={e => setTexto(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar() } }} />
        <div className="pie apagado">
          <span>Intro para enviar · Mayús+Intro, nueva línea</span>
          <button className="boton principal" disabled={!texto.trim() || pensando} onClick={() => enviar()}>Enviar</button>
        </div>
      </div>
    </aside>
  )
}

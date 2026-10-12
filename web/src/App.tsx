import { useCallback, useEffect, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { api } from './api'
import type { Convenio, ConvenioResumen, Estado, Hoja, Incumplimiento, MensajeModelo, RespuestaAccion } from './api'
import { Chat } from './Chat'
import type { Item } from './Chat'
import { DialogoAusencia, DialogoConvenio, DialogoNivel } from './Dialogos'
import type { DatosAusencia } from './Dialogos'
import { clave, DIAS, diaSemana, fmt, LEYENDA, NOMBRE_DIA, VistaDia, VistaSemana } from './Hoja'
import type { Seleccion } from './Hoja'
import { Cajon } from './Cajon'
import type { Pestana } from './Cajon'

// La demo vive en este día: decide el aviso por defecto de una ausencia y desde dónde entiende el
// asistente "mañana" o "el jueves". El aviso de cada ausencia se puede cambiar en su diálogo.
const HOY = '2026-11-09'

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

interface Pendiente { nivel: 'bloqueo' | 'acuerdo'; que: string; persona: string; incidencias: Incumplimiento[]; nombre: string; args: Record<string, unknown> }
interface Aviso { texto: string; detalle?: string; deshacer?: boolean }

/** Número de semana ISO 8601, el de los calendarios: el 9/11/2026 cae en la 46. */
function semanaISO(f: Date) {
  const d = new Date(Date.UTC(f.getFullYear(), f.getMonth(), f.getDate()))
  d.setUTCDate(d.getUTCDate() + 3 - (d.getUTCDay() + 6) % 7) // el jueves de esa semana
  return 1 + Math.floor((d.getTime() - Date.UTC(d.getUTCFullYear(), 0, 1)) / 864e5 / 7)
}

export default function App() {
  const [convenios, setConvenios] = useState<ConvenioResumen[]>([])
  // ?convenio=BOE-… abre la hoja directamente, sin el diálogo (para grabar la demo).
  const inicial = new URLSearchParams(location.search).get('convenio')
  const [elegir, setElegir] = useState(!inicial)
  const [convenio, setConvenio] = useState<Convenio | null>(null)
  const [hoja, setHoja] = useState<Hoja | null>(null)
  const [estado, setEstado] = useState<Estado | null>(null)
  const [historial, setHistorial] = useState<Estado[]>([])
  const [incs, setIncs] = useState<Incumplimiento[]>([])
  const [resaltar, setResaltar] = useState<[string, number][]>([])
  const [semana, setSemana] = useState(0)
  const [vista, setVista] = useState<'semana' | number>('semana') // la semana o un día (índice en fechas)
  const [seleccion, setSeleccion] = useState<Seleccion | null>(null)
  const [editor, setEditor] = useState<{ s: Seleccion; x: number; y: number; texto: string } | null>(null)
  const [menu, setMenu] = useState<{ s: Seleccion; x: number; y: number } | null>(null)
  const [ausencia, setAusencia] = useState<Seleccion | null>(null)
  const [pendiente, setPendiente] = useState<Pendiente | null>(null)
  const [aviso, setAviso] = useState<Aviso | null>(null)
  const [cajon, setCajon] = useState<Pestana | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [chatAbierto, setChatAbierto] = useState(true)
  const [items, setItems] = useState<Item[]>([])
  const [mensajes, setMensajes] = useState<MensajeModelo[]>([])
  const [pensando, setPensando] = useState(false)
  const editorRef = useRef<HTMLInputElement>(null)

  useEffect(() => { api.convenios().then(setConvenios).catch(e => setError(String(e))) }, [])

  // Al abrir un convenio: sus reglas, la hoja y el cuadrante de partida.
  const abrir = useCallback(async (boe: string) => {
    setError(null)
    try {
      const [c, h] = await Promise.all([api.convenio(boe), api.hoja(boe)])
      setConvenio(c); setHoja(h)
      setEstado({ boe, cuadrante: h.cuadrante, ausencias: [], acuerdos: [], clases: {} })
      setHistorial([]); setIncs(h.incumplimientos); setResaltar([])
      setSemana(Math.max(0, h.semanas.findIndex(s => s.includes(h.fechas.indexOf(HOY)))))
      setVista('semana'); setSeleccion(null)
    } catch (e) {
      setError(String(e))
    }
  }, [])
  useEffect(() => { if (inicial) abrir(inicial) }, [inicial, abrir])

  // Si una acción cambia de convenio, la hoja (contratos, reglas) se recarga y el estado se queda.
  useEffect(() => {
    if (!estado || !convenio || estado.boe === convenio.boe) return
    Promise.all([api.convenio(estado.boe), api.hoja(estado.boe)]).then(([c, h]) => { setConvenio(c); setHoja(h) })
  }, [estado, convenio])

  const hoy = hoja ? hoja.fechas.indexOf(HOY) : -1
  const hoyISO = HOY
  const dias = hoja?.semanas[semana] ?? []

  function irA(fecha: string | null | undefined) {
    if (!hoja || !fecha) return
    const d = hoja.fechas.indexOf(fecha)
    if (d < 0) return
    setSemana(hoja.semanas.findIndex(s => s.includes(d)))
    if (vista !== 'semana') setVista(d)
  }

  function aplicar(r: RespuestaAccion) {
    setEstado(r.estado); setHistorial(r.historial); setIncs(r.incumplimientos); setResaltar(r.resaltar)
    irA(r.ir_a)
  }

  async function accion(nombre: string, args: Record<string, unknown>) {
    if (!estado || !hoja) return
    setOcupado(true); setMenu(null)
    try {
      const r = await api.accion(estado, historial, nombre, args, hoyISO)
      if (r.nivel === 'bloqueo' || r.nivel === 'acuerdo') {
        setPendiente({ nivel: r.nivel, que: r.texto.split('\n')[0], persona: String(args.persona ?? ''), incidencias: r.incidencias ?? [], nombre, args })
        irA(r.ir_a)
        return
      }
      const cambio = r.historial.length !== historial.length
      aplicar(r)
      if (nombre === 'deshacer') setAviso({ texto: 'Deshecho.' })
      else if (r.nivel === 'aviso') setAviso({ texto: 'Hecho, con avisos.', detalle: (r.incidencias ?? []).map(i => i.mensaje).slice(0, 3).join(' · '), deshacer: true })
      else {
        // La primera línea dice qué se hizo; las demás, a quién se movió o por qué no hizo falta.
        const [cabeza, ...resto] = r.texto.split('\n')
        setAviso({ texto: cabeza, detalle: resto.slice(0, 4).join('\n') || undefined, deshacer: cambio })
      }
    } catch (e) {
      setAviso({ texto: String(e) })
    } finally {
      setOcupado(false)
    }
  }

  async function enviar(texto: string) {
    if (!estado || pensando) return
    setItems(it => [...it, { tipo: 'usuario', texto }])
    setPensando(true)
    try {
      await api.agente(estado, historial, mensajes, texto, hoyISO, ev => {
        if (ev.tipo === 'accion') setItems(it => [...it, { tipo: 'paso', nombre: ev.nombre, texto: ev.texto, nivel: ev.nivel }])
        else if (ev.tipo === 'error') setItems(it => [...it, { tipo: 'error', texto: ev.texto }])
        else {
          setEstado(ev.estado); setHistorial(ev.historial); setIncs(ev.incumplimientos); setMensajes(ev.mensajes)
          if (ev.resaltar.length) setResaltar(ev.resaltar)
          irA(ev.ir_a)
          if (ev.respuesta) setItems(it => [...it, { tipo: 'asistente', texto: ev.respuesta }])
        }
      })
    } catch (e) {
      setItems(it => [...it, { tipo: 'error', texto: String(e) }])
    } finally {
      setPensando(false)
    }
  }

  function abrirEditor(s: Seleccion, inicial?: string) {
    if (!estado) return
    const el = document.querySelector(`[data-celda="${CSS.escape(clave(s.persona, s.dia))}"]`)
    const r = el?.getBoundingClientRect()
    const t = estado.cuadrante[s.persona][s.dia]
    setEditor({ s, x: r?.left ?? 200, y: r?.top ?? 200, texto: inicial ?? (t ? fmt(t).replace('–', '-') : '') })
    requestAnimationFrame(() => { if (!inicial) editorRef.current?.select() })
  }

  function cambiarTurno(s: Seleccion, turno: string) {
    if (!hoja) return
    accion('cambiar_turno', { persona: s.persona, dia: hoja.fechas[s.dia], turno: turno.trim() || 'libre' })
  }

  // Teclado de hoja de cálculo sobre la celda seleccionada.
  useEffect(() => {
    function tecla(e: KeyboardEvent) {
      const a = document.activeElement
      const enCampo = a instanceof HTMLInputElement || a instanceof HTMLTextAreaElement || a instanceof HTMLSelectElement
      if (e.defaultPrevented || enCampo || editor || pendiente || ausencia || elegir || !estado || !hoja) return
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); if (historial.length) accion('deshacer', {}); return }
      if (!seleccion || e.ctrlKey || e.metaKey || e.altKey) return
      const personas = hoja.plantilla.map(p => p.nombre)
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); cambiarTurno(seleccion, 'libre') }
      else if (e.key === 'Enter' || e.key === 'F2') { e.preventDefault(); abrirEditor(seleccion) }
      else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const i = personas.indexOf(seleccion.persona) + (e.key === 'ArrowDown' ? 1 : -1)
        if (personas[i]) setSeleccion({ ...seleccion, persona: personas[i] })
      } else if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && vista === 'semana') {
        e.preventDefault()
        const d = seleccion.dia + (e.key === 'ArrowRight' ? 1 : -1)
        if (dias.includes(d)) setSeleccion({ ...seleccion, dia: d })
      } else if (/^[0-9a-zñ]$/i.test(e.key)) { e.preventDefault(); abrirEditor(seleccion, e.key) }
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  })

  useEffect(() => {
    if (!aviso) return
    const t = setTimeout(() => setAviso(null), aviso.deshacer ? 8000 : 5000)
    return () => clearTimeout(t)
  }, [aviso])

  if (!estado || !hoja || !convenio) {
    return (
      <div className="app sin-chat">
        <div className="barra"><span className="marca">Cuadrante</span></div>
        <div className="centro">
          {error ? <p className="cargando" style={{ color: 'var(--mal)' }}>{error}</p> : !elegir && <p className="cargando">Abriendo el cuadrante…</p>}
        </div>
        {elegir && convenios.length > 0 && (
          <DialogoConvenio convenios={convenios} actual={null} onElegir={b => { setElegir(false); abrir(b) }} />
        )}
      </div>
    )
  }

  const abiertos = incs.filter(i => !i.pactado).length
  const primero = new Date(hoja.fechas[dias[0]]), ultimo = new Date(hoja.fechas[dias[dias.length - 1]])
  const mes = (f: Date) => MESES[f.getMonth()]
  const rango = primero.getMonth() === ultimo.getMonth()
    ? `${primero.getDate()}–${ultimo.getDate()} ${mes(ultimo).slice(0, 3)}`
    : `${primero.getDate()} ${mes(primero).slice(0, 3)}–${ultimo.getDate()} ${mes(ultimo).slice(0, 3)}`
  // Lo que se está viendo y tocando, escrito entero encima de la rejilla.
  const titulo = vista === 'semana'
    ? `Semana ${semanaISO(primero)} · ${primero.getDate()}${primero.getMonth() === ultimo.getMonth() ? '' : ` de ${mes(primero)}`} al ${ultimo.getDate()} de ${mes(ultimo)}`
    : `${NOMBRE_DIA[diaSemana(hoja.fechas[vista])].replace(/^./, c => c.toUpperCase())} ${new Date(hoja.fechas[vista]).getDate()} de ${mes(new Date(hoja.fechas[vista]))}`
  const props = {
    hoja, estado, hoy, seleccion,
    resaltar: new Set(resaltar.map(([p, d]) => clave(p, d))),
    pactadas: new Set(estado.acuerdos.flatMap(a => a.dias.map(d => clave(a.persona, d)))),
    onSeleccion: (s: Seleccion) => { setSeleccion(s); setMenu(null) },
    onEditar: (s: Seleccion) => abrirEditor(s),
    onMenu: (s: Seleccion, e: MouseEvent) => setMenu({ s, x: e.clientX, y: e.clientY }),
  }
  const moverSemana = (n: number) => { setSemana(n); if (vista !== 'semana') setVista(hoja.semanas[n][0]) }

  return (
    <div className={`app ${chatAbierto ? '' : 'sin-chat'}`}>
      <div className="barra">
        <span className="marca">Cuadrante</span>
        <button className="chip" onClick={() => setElegir(true)} title="Cambiar de convenio">{convenio.nombre}</button>
        <div className="grupo">
          <button className="chip" disabled={semana === 0} onClick={() => moverSemana(semana - 1)} aria-label="Semana anterior">‹</button>
          <span className="semana">Semana {semanaISO(primero)} <span className="rango">· {rango}</span></span>
          <button className="chip" disabled={semana === hoja.semanas.length - 1} onClick={() => moverSemana(semana + 1)} aria-label="Semana siguiente">›</button>
        </div>
        <div className="grupo">
          <button className="chip" aria-pressed={vista === 'semana'} onClick={() => setVista('semana')}>Semana</button>
          {dias.map(d => (
            <button key={d} className="chip" aria-pressed={vista === d} onClick={() => setVista(d)}
              title={`${NOMBRE_DIA[diaSemana(hoja.fechas[d])]} ${new Date(hoja.fechas[d]).getDate()}`}>
              {DIAS[diaSemana(hoja.fechas[d])]} {new Date(hoja.fechas[d]).getDate()}
            </button>
          ))}
        </div>
        <button className="chip empuja" disabled={!historial.length || ocupado} onClick={() => accion('deshacer', {})} title="Ctrl+Z">Deshacer</button>
        <button className={`chip estado-cuadrante ${abiertos ? 'mal' : ''}`} onClick={() => setCajon('problemas')}>
          <span className="bola" />{abiertos ? `${abiertos} incumplimientos` : 'Cumple el convenio'}
        </button>
        <button className="chip" onClick={() => setCajon(cajon === 'convenio' ? null : 'convenio')}>Reglas</button>
        {!chatAbierto && <button className="chip" onClick={() => setChatAbierto(true)}>Asistente</button>}
      </div>

      <div className="leyenda">
        <h1 className="titulo">{titulo}{vista !== 'semana' && vista === hoy && <small> · hoy</small>}</h1>
        {LEYENDA.map(([c, n]) => <span key={c}><i className={`c-${c}`} />{n}</span>)}
        <span><i className="libre" />Libre</span>
        <span><span className="marca-resaltado" />Último cambio</span>
        <span className="apagado ayuda">
          {ocupado ? 'Calculando…' : 'Doble clic o escribe sobre una celda · clic derecho para más'}
        </span>
      </div>

      <main className="centro" onMouseDown={() => setMenu(null)}>
        {vista === 'semana' ? <VistaSemana {...props} semana={dias} /> : <VistaDia {...props} dia={vista} />}
      </main>

      {chatAbierto && <Chat items={items} pensando={pensando} onEnviar={enviar} onCerrar={() => setChatAbierto(false)} />}

      {editor && (
        <input ref={editorRef} className="cifra" aria-label="Turno"
          style={{ position: 'fixed', left: editor.x, top: editor.y, zIndex: 35, width: 150, padding: '6px 8px', border: '2px solid var(--negro)', borderRadius: 6, background: '#fff' }}
          value={editor.texto} placeholder="7-15, tarde, libre…" autoFocus
          onChange={e => setEditor({ ...editor, texto: e.target.value })}
          onBlur={() => setEditor(null)}
          onKeyDown={e => {
            // preventDefault: que el atajo global de la hoja (Intro edita la celda) no lo reabra
            if (e.key === 'Escape') { e.preventDefault(); setEditor(null) }
            if (e.key === 'Enter') { e.preventDefault(); const { s, texto } = editor; setEditor(null); cambiarTurno(s, texto) }
          }} />
      )}

      {menu && (
        <div className="menu-ctx" style={{ left: menu.x, top: menu.y }}>
          <button onClick={() => { setMenu(null); abrirEditor(menu.s) }}>Cambiar turno…</button>
          <button onClick={() => cambiarTurno(menu.s, 'libre')}>Dejar libre</button>
          <button onClick={() => { setMenu(null); setAusencia(menu.s) }}>Marcar ausencia…</button>
        </div>
      )}

      {cajon && <Cajon pestana={cajon} convenio={convenio} hoja={hoja} incumplimientos={incs} acuerdos={estado.acuerdos} onPestana={setCajon} onCerrar={() => setCajon(null)} />}

      {ausencia && (
        <DialogoAusencia hoja={{ ...hoja, cuadrante: estado.cuadrante }} persona={ausencia.persona} dia={ausencia.dia} hoy={hoyISO}
          onCerrar={() => setAusencia(null)}
          onAceptar={(a: DatosAusencia) => { setAusencia(null); accion('marcar_ausencia', { ...a }) }} />
      )}

      {pendiente && (
        <DialogoNivel {...pendiente}
          onCerrar={() => setPendiente(null)}
          onAcordar={() => { const p = pendiente; setPendiente(null); accion(p.nombre, { ...p.args, con_acuerdo: true }) }} />
      )}

      {elegir && (
        <DialogoConvenio convenios={convenios} actual={estado.boe}
          onElegir={b => { setElegir(false); if (b !== estado.boe) accion('cambiar_convenio', { convenio: b }) }}
          onCerrar={() => setElegir(false)} />
      )}

      {aviso && (
        <div className="aviso-flotante" role="status">
          <span>{aviso.texto}</span>
          {aviso.detalle && <span className="detalle">{aviso.detalle}</span>}
          {aviso.deshacer && (
            <div className="acciones">
              <button className="boton" onClick={() => { setAviso(null); accion('deshacer', {}) }}>Deshacer</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

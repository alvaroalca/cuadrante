import { useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent as TeclaReact, MouseEvent } from 'react'
import { api, articulo, NOMBRE_CLASE } from './api'
import type { Acuerdo, Ausencia, Clase, Convenio, ConvenioResumen, Cuadrante, Edicion, Hoja, Incumplimiento, Regla, Replan, Turno } from './api'
import { DialogoAusencia, DialogoConvenio, DialogoEdicion } from './Dialogos'
import { clave, fmt, horas, VistaDia, VistaSemana } from './Hoja'
import type { Seleccion } from './Hoja'
import { Panel } from './Panel'
import type { NotaDatos } from './Panel'

const DIAS = 'LMXJVSD'
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
const COL = (i: number) => (i < 26 ? String.fromCharCode(65 + i) : 'AA')

/** "7-15", "07–15", "7 a 15"; "22-6" cruza la medianoche. Vacío o "libre": libra. undefined: no se entiende. */
function leerTurno(texto: string): Turno | null | undefined {
  const t = texto.trim().toLowerCase()
  if (!t || t === 'libre') return null
  const m = t.match(/^(\d{1,2})(?::00)?\s*(?:-|–|a)\s*(\d{1,2})(?::00)?$/)
  if (!m) return undefined
  const a = Number(m[1]), b = Number(m[2])
  if (a > 23 || b > 24 || a === b) return undefined
  return [a, b > a ? b : b + 24]
}

const igual = (a: Turno | null, b: Turno | null) => (a ? !!b && a[0] === b[0] && a[1] === b[1] : !b)
const claveInc = (i: Incumplimiento) => `${i.tipo}|${i.persona}|${i.dias.join(',')}|${i.mensaje}`

interface Pendiente { persona: string; dia: number; antes: Turno | null; despues: Turno | null; edicion: Edicion }
/** Celda editada a mano: lo que había al principio y las reglas que se pactaron para dejarla así. */
interface Editada { persona: string; dia: number; antes: Turno | null; despues: Turno | null; pactos: Regla[] }

function Icono() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <rect width="16" height="16" fill="#fff" stroke="#808080" />
      <path d="M0 5.5h16M0 10.5h16M5.5 0v16M10.5 0v16" stroke="#c0c0c0" />
      <rect x="6" y="6" width="4" height="4" fill="#ffff99" stroke="#000" />
    </svg>
  )
}

export default function App() {
  const [convenios, setConvenios] = useState<ConvenioResumen[]>([])
  // ?convenio=BOE-… abre la hoja directamente, sin el diálogo (para grabar la demo).
  const inicial = new URLSearchParams(location.search).get('convenio')
  const [boe, setBoe] = useState<string | null>(inicial)
  const [elegir, setElegir] = useState(!inicial)
  const [convenio, setConvenio] = useState<Convenio | null>(null)
  const [hoja, setHoja] = useState<Hoja | null>(null)
  const [cuadrante, setCuadrante] = useState<Cuadrante | null>(null)
  const [ausencias, setAusencias] = useState<Ausencia[]>([])
  const [incs, setIncs] = useState<Incumplimiento[]>([])
  const [acuerdos, setAcuerdos] = useState<Acuerdo[]>([])
  const [editadas, setEditadas] = useState<Editada[]>([])
  const [pendiente, setPendiente] = useState<Pendiente | null>(null)
  const [avisos, setAvisos] = useState<Incumplimiento[]>([]) // los de la última edición
  const [texto, setTexto] = useState<string | null>(null) // lo que se escribe en la barra de fórmulas
  const entrada = useRef<HTMLInputElement>(null)
  const [semana, setSemana] = useState(0)
  const [vista, setVistaSola] = useState<number | 'semana'>(0) // día de la semana (0-6) o la semana entera
  const [seleccion, setSeleccion] = useState<Seleccion | null>(null)
  const setVista = (v: number | 'semana') => { setVistaSola(v); setSeleccion(null) }
  const [nota, setNota] = useState<NotaDatos | null>(null)
  const [dialogoAusencia, setDialogoAusencia] = useState<{ persona: string; dia: number } | null>(null)
  const [nuevaAusencia, setNuevaAusencia] = useState<Ausencia | null>(null)
  const [propuesta, setPropuesta] = useState<Replan | null>(null)
  const [calculando, setCalculando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { api.convenios().then(setConvenios).catch(e => setError(String(e))) }, [])

  useEffect(() => {
    if (!boe) return
    setHoja(null); setConvenio(null); setPropuesta(null); setAusencias([]); setSeleccion(null)
    setAcuerdos([]); setEditadas([]); setAvisos([]); setPendiente(null)
    Promise.all([api.convenio(boe), api.hoja(boe)]).then(([c, h]) => {
      setConvenio(c); setHoja(h); setCuadrante(h.cuadrante); setIncs(h.incumplimientos)
    }).catch(e => setError(String(e)))
  }, [boe])

  const dias = hoja?.semanas[semana] ?? []
  const dia = vista === 'semana' ? null : dias[vista]
  const mostrado = propuesta?.cuadrante ?? cuadrante
  const cambios = propuesta?.cambios ?? []
  const incumplimientos = incs.filter(i => !i.pactado).length
  // Celda de una persona seleccionada: la que se edita.
  const celda = seleccion && seleccion.fila !== 'faltan' && seleccion.fila !== 'hay'
    ? { persona: seleccion.fila, dia: vista === 'semana' ? seleccion.col : dia! } : null
  const turnoCelda = celda && mostrado ? mostrado[celda.persona][celda.dia] : null
  const valorCelda = turnoCelda ? fmt(turnoCelda) : ''

  function empezar(inicial?: string) {
    if (!celda || propuesta) return
    setTexto(inicial ?? valorCelda)
    requestAnimationFrame(() => entrada.current?.focus())
  }

  async function editar(turno: Turno | null) {
    if (!boe || !cuadrante || !celda || propuesta) return
    const { persona, dia: d } = celda
    const antes = cuadrante[persona][d]
    if (igual(antes, turno)) return
    setError(null)
    try {
      const edicion = await api.editar(boe, cuadrante, persona, d, turno, ausencias, acuerdos)
      const p = { persona, dia: d, antes, despues: turno, edicion }
      if (edicion.nivel === 'ok' || edicion.nivel === 'aviso') aplicarEdicion(p, false)
      else setPendiente(p)
    } catch (e) {
      setError(String(e))
    }
  }

  function aplicarEdicion(p: Pendiente, acordada: boolean) {
    const pactados = acordada ? p.edicion.nuevos.filter(i => i.nivel === 'acuerdo') : []
    const claves = new Set(pactados.map(claveInc))
    setCuadrante(p.edicion.cuadrante)
    setIncs(p.edicion.incumplimientos.map(i => (claves.has(claveInc(i)) ? { ...i, pactado: true } : i)))
    setAcuerdos([...acuerdos, ...pactados.map(i => ({ persona: i.persona!, tipo: i.tipo, dias: i.dias, mensaje: i.mensaje }))])
    const previa = editadas.find(e => e.persona === p.persona && e.dia === p.dia)
    const reglas = [...(previa?.pactos ?? []), ...pactados.map(i => i.regla!)]
    setEditadas([...editadas.filter(e => e !== previa), {
      persona: p.persona, dia: p.dia, antes: previa ? previa.antes : p.antes, despues: p.despues,
      pactos: reglas.filter((r, i) => reglas.findIndex(x => x.tipo === r.tipo) === i),
    }])
    setAvisos(p.edicion.nuevos.filter(i => i.nivel === 'aviso'))
    setPendiente(null)
  }

  // Teclado de hoja de cálculo sobre la celda seleccionada: Supr libra, F2 o Intro editan, una cifra empieza a escribir.
  useEffect(() => {
    function tecla(e: KeyboardEvent) {
      if (!celda || propuesta || pendiente || dialogoAusencia || elegir || document.activeElement === entrada.current) return
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); editar(null) }
      else if (e.key === 'F2' || e.key === 'Enter') { e.preventDefault(); empezar() }
      else if (/^[0-9]$/.test(e.key)) { e.preventDefault(); empezar(e.key) }
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  })

  function teclaEntrada(e: TeclaReact<HTMLInputElement>) {
    if (e.key === 'Escape') { setTexto(null); entrada.current?.blur() }
    if (e.key !== 'Enter') return
    const turno = leerTurno(texto ?? '')
    if (turno === undefined) {
      setError(`«${texto}» no es un turno. Escribe 7-15, 22-6 para una noche o déjalo vacío para librar.`)
      return
    }
    setTexto(null); entrada.current?.blur()
    editar(turno)
  }

  async function cubrir(a: Ausencia) {
    if (!boe || !cuadrante) return
    setDialogoAusencia(null); setNuevaAusencia(a); setPropuesta(null); setCalculando(true); setError(null)
    const d = hoja!.fechas.indexOf(a.fecha)
    setSemana(hoja!.semanas.findIndex(s => s.includes(d)))
    setVista((new Date(a.fecha).getDay() + 6) % 7)
    try {
      setPropuesta(await api.replanificar(boe, cuadrante, [...ausencias, a], acuerdos))
    } catch (e) {
      setError(String(e))
    } finally {
      setCalculando(false)
    }
  }

  function aplicar() {
    if (!propuesta?.cuadrante || !nuevaAusencia) return
    setCuadrante(propuesta.cuadrante)
    setAusencias([...ausencias, nuevaAusencia])
    setIncs(propuesta.incumplimientos)
    setPropuesta(null); setNuevaAusencia(null); setAvisos([])
  }

  function descartar() { setPropuesta(null); setNuevaAusencia(null); setError(null) }

  // Nota de una celda cambiada: qué clase de hora es y de qué regla sale; o qué se editó a mano y con qué acuerdo.
  function notaCambio(e: MouseEvent, persona: string, d: number) {
    const c = cambios.find(x => x.persona === persona && x.dia === d)
    const ed = editadas.find(x => x.persona === persona && x.dia === d)
    if ((!c || !propuesta) && ed) {
      setNota({
        x: e.clientX, y: e.clientY,
        titulo: `Editado a mano: ${ed.antes ? fmt(ed.antes) : 'libre'} → ${ed.despues ? fmt(ed.despues) : 'libre'}`,
        texto: ed.pactos.length
          ? `Con acuerdo de ${persona}. ${ed.pactos.map(r => `${articulo({ ...r, cita: r.cita_pacto ?? r.cita })}: «${(r.cita_pacto ?? r.cita).texto}»`).join(' ')}`
          : 'Sin nada que pactar.',
      })
      return
    }
    if (!c || !propuesta) return
    const clases = Object.entries(c.horas) as [Clase, number][]
    const reglas = clases.map(([cl]) => propuesta.opciones[persona].find(o => o.clase === cl)?.regla).filter(Boolean)
    setNota({
      x: e.clientX, y: e.clientY,
      titulo: `${persona}: ${c.antes ? fmt(c.antes) : 'libre'} → ${fmt(c.despues)}`,
      texto: clases.map(([cl, h]) => `+${h} h ${NOMBRE_CLASE[cl].toLowerCase()}`).join(', ')
        + (reglas.length ? `. ${reglas.map(r => `${articulo(r!)}: «${r!.cita.texto}»`).join(' ')}` : ''),
    })
  }

  // Barra de fórmulas: dirección de la celda y lo que hay en ella.
  const formula = useMemo(() => {
    if (!hoja || !mostrado || !seleccion) return { celda: '', texto: '', cita: '' }
    const filas = hoja.plantilla.map(p => p.nombre)
    const fila = seleccion.fila === 'faltan' ? filas.length + 3 : seleccion.fila === 'hay' ? filas.length + 4 : filas.indexOf(seleccion.fila) + 2
    const col = vista === 'semana' ? dias.indexOf(seleccion.col) : seleccion.col
    const celda = `${COL(col + 2)}${fila}`
    const d = vista === 'semana' ? seleccion.col : dia!
    if (seleccion.fila === 'faltan' || seleccion.fila === 'hay') {
      const h = seleccion.col
      return { celda, texto: `=COBERTURA(${String(h).padStart(2, '0')}:00)  hacen falta ${hoja.necesidad[d][h]}`, cita: '' }
    }
    const t = mostrado[seleccion.fila][d]
    const c = cambios.find(x => x.persona === seleccion.fila && x.dia === d)
    const aus = ausencias.find(a => a.persona === seleccion.fila && a.fecha === hoja.fechas[d]) ?? (nuevaAusencia?.persona === seleccion.fila && nuevaAusencia.fecha === hoja.fechas[d] ? nuevaAusencia : null)
    if (!t) return { celda, texto: `${seleccion.fila} · libra`, cita: '' }
    let texto = `${seleccion.fila} · ${horas(t)} h`
    let cita = ''
    if (aus) texto += ` · ausente (${aus.motivo}${aus.desde != null ? ` ${aus.desde}–${aus.hasta}` : ''})`
    if (c && propuesta) {
      const [[cl, hh]] = Object.entries(c.horas) as [Clase, number][]
      const r = propuesta.opciones[seleccion.fila].find(o => o.clase === cl)?.regla
      texto += ` · +${hh} h ${NOMBRE_CLASE[cl].toLowerCase()}`
      if (r) cita = `${articulo(r)}: «${r.cita.texto}»`
    }
    return { celda, texto, cita }
  }, [hoja, mostrado, seleccion, vista, dia, dias, cambios, ausencias, nuevaAusencia, propuesta])

  const suma = hoja && mostrado && seleccion && hoja.plantilla.some(p => p.nombre === seleccion.fila)
    ? dias.reduce((s, d) => s + horas(mostrado[seleccion.fila][d]), 0) : null

  const mes = hoja ? MESES[new Date(hoja.fechas[0]).getMonth()] : ''
  const props = hoja && mostrado ? {
    hoja, cuadrante: mostrado, cambios, seleccion,
    editadas: new Set(editadas.map(e => clave(e.persona, e.dia))),
    onEditar: () => empezar(),
    ausencias: nuevaAusencia ? [...ausencias, nuevaAusencia] : ausencias,
    onSeleccion: setSeleccion,
    onAusencia: (persona: string, d: number) => setDialogoAusencia({ persona, dia: d }),
    onNota: notaCambio,
    onSinNota: () => setNota(null),
  } : null

  return (
    <div className="ventana">
      <div className="titulo">
        <Icono />
        <span>Cuadrante</span>
        {convenio && <span className="sub">— {convenio.nombre.toLowerCase()} · {mes} 2026</span>}
      </div>

      <nav className="menu">
        <button onClick={() => setElegir(true)}><u>C</u>onvenio…</button>
        <button onClick={() => hoja && seleccion && seleccion.fila !== 'faltan' && seleccion.fila !== 'hay'
          ? setDialogoAusencia({ persona: seleccion.fila, dia: vista === 'semana' ? seleccion.col : dia! })
          : hoja && setDialogoAusencia({ persona: hoja.plantilla[0].nombre, dia: dia ?? dias[0] })}>
          <u>I</u>nsertar ausencia…
        </button>
        <button onClick={() => setVista(vista === 'semana' ? 0 : 'semana')}><u>V</u>er {vista === 'semana' ? 'día' : 'semana'}</button>
      </nav>

      <div className="herramientas">
        <label>Semana
          <select value={semana} onChange={e => { setSemana(Number(e.target.value)); setSeleccion(null) }} disabled={!hoja}>
            {hoja?.semanas.map((s, i) => {
              const a = new Date(hoja.fechas[s[0]]), b = new Date(hoja.fechas[s[s.length - 1]])
              return <option key={i} value={i}>{a.getDate()}–{b.getDate()} de {MESES[b.getMonth()]}</option>
            })}
          </select>
        </label>
        <span className="sep" />
        <span className="apagado">{hoja ? `${hoja.plantilla.length} personas · apertura de ${hoja.apertura.desde} a ${hoja.apertura.hasta}` : ''}</span>
        <div className="leyenda">
          <span><i style={{ background: 'var(--manana)' }} />Mañana</span>
          <span><i style={{ background: 'var(--tarde)' }} />Tarde</span>
          <span><i style={{ background: 'var(--noche)' }} />Noche</span>
          <span><i style={{ background: 'var(--ausencia)' }} />Ausencia</span>
          <span><i style={{ background: 'var(--propuesta)' }} />Propuesta</span>
        </div>
      </div>

      <div className="formula">
        <div className="nombre-celda hundido">{formula.celda}</div>
        <div className="fx">fx</div>
        <div className="contenido hundido">
          {celda && (
            <input ref={entrada} aria-label="Turno" placeholder="libre" readOnly={!!propuesta}
              value={texto ?? valorCelda} onFocus={() => texto === null && !propuesta && setTexto(valorCelda)}
              onChange={e => setTexto(e.target.value)} onKeyDown={teclaEntrada} onBlur={() => setTexto(null)} />
          )}
          {formula.texto}<span className="cita">{formula.cita}</span>
        </div>
      </div>

      <div className="trabajo">
        <main className="hoja">
          {props && (vista === 'semana'
            ? <VistaSemana {...props} semana={dias} />
            : <VistaDia {...props} dia={dia!} />)}
          {!hoja && boe && !error && <p style={{ padding: 16 }} className="apagado">Abriendo el cuadrante…</p>}
        </main>
        {convenio && hoja
          ? <Panel convenio={convenio} hoja={hoja} incumplimientos={incumplimientos} pactados={incs.length - incumplimientos}
              acuerdos={acuerdos} avisos={avisos} ausencias={ausencias}
              propuesta={propuesta} nuevaAusencia={nuevaAusencia} calculando={calculando} error={error}
              onNota={setNota} onAplicar={aplicar} onDescartar={descartar}
              onAusencia={() => setDialogoAusencia({ persona: hoja.plantilla[0].nombre, dia: dia ?? dias[0] })} />
          : <aside className="panel">{error && <section><p className="error">{error}</p></section>}</aside>}
      </div>

      <div className="pestanas">
        <div className="flechas">
          <button className="boton" disabled={semana === 0} onClick={() => setSemana(semana - 1)} aria-label="Semana anterior">◄</button>
          <button className="boton" disabled={!hoja || semana === hoja.semanas.length - 1} onClick={() => setSemana(semana + 1)} aria-label="Semana siguiente">►</button>
        </div>
        <div className={`pestana ${vista === 'semana' ? 'activa' : ''}`} onClick={() => setVista('semana')}>Semana</div>
        {hoja && dias.map((d, i) => {
          const f = new Date(hoja.fechas[d])
          return (
            <div key={d} className={`pestana ${vista === i ? 'activa' : ''}`} onClick={() => setVista(i)}>
              <span className={i >= 5 ? 'finde' : ''}>{DIAS[i]} {f.getDate()}</span>
            </div>
          )
        })}
      </div>

      <div className="estado">
        <div className={`hundido ${calculando ? 'reloj' : ''}`} style={{ background: 'none' }}>{calculando ? 'Calculando…' : error ? 'Error' : 'Listo'}</div>
        <div className="hundido" style={{ background: 'none' }}>Incumplimientos: {propuesta ? propuesta.incumplimientos.filter(i => !i.pactado).length : incumplimientos}</div>
        <div className="hundido" style={{ background: 'none' }}>{suma != null ? `Suma semana: ${suma} h` : ' '}</div>
        <div className="hundido" style={{ background: 'none' }}>{convenio?.boe ?? ''}</div>
      </div>

      {nota && (
        <div className="nota" style={{ left: Math.min(nota.x + 14, window.innerWidth - 340), top: nota.y + 14 }}>
          <b>{nota.titulo}</b>
          {nota.cita ? <q>{nota.texto}</q> : <span>{nota.texto}</span>}
        </div>
      )}

      {elegir && convenios.length > 0 && (
        <DialogoConvenio convenios={convenios} actual={boe}
          onElegir={b => { setBoe(b); setElegir(false) }}
          onCerrar={boe ? () => setElegir(false) : undefined} />
      )}
      {pendiente && hoja && (
        <DialogoEdicion persona={pendiente.persona} antes={pendiente.antes} despues={pendiente.despues} edicion={pendiente.edicion}
          dia={`${DIAS[(new Date(hoja.fechas[pendiente.dia]).getDay() + 6) % 7]} ${new Date(hoja.fechas[pendiente.dia]).getDate()}`}
          onAcordar={() => aplicarEdicion(pendiente, true)} onCerrar={() => setPendiente(null)} />
      )}
      {dialogoAusencia && hoja && mostrado && (
        <DialogoAusencia hoja={{ ...hoja, cuadrante: mostrado }} persona={dialogoAusencia.persona} dia={dialogoAusencia.dia}
          onAceptar={cubrir} onCerrar={() => setDialogoAusencia(null)} />
      )}
    </div>
  )
}

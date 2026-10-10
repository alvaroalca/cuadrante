import type { MouseEvent } from 'react'
import { articulo, NOMBRE_CLASE } from './api'
import type { Acuerdo, Ausencia, Clase, Convenio, Hoja, Incumplimiento, Regla, Replan } from './api'
import { agrupar, Incidencia } from './Dialogos'
import { fmt } from './Hoja'
import { enunciado } from './reglas'

export interface NotaDatos { x: number; y: number; titulo: string; texto: string; cita?: boolean }

const CLASES: Clase[] = ['redistribucion', 'voluntarias', 'pactadas', 'extras']
const CORTO: Record<Clase, string> = { redistribucion: 'Redist.', voluntarias: 'Volunt.', pactadas: 'Pactad.', extras: 'Extras' }

export function notaDeRegla(e: MouseEvent, r: Regla, titulo?: string): NotaDatos {
  return { x: e.clientX, y: e.clientY, titulo: titulo ?? `${articulo(r)} · ${r.origen === 'estatuto' ? 'Estatuto de los Trabajadores' : 'convenio'}`, texto: r.cita.texto, cita: true }
}

interface Props {
  convenio: Convenio
  hoja: Hoja
  incumplimientos: number
  pactados: number
  acuerdos: Acuerdo[]
  avisos: Incumplimiento[]
  ausencias: Ausencia[]
  propuesta: Replan | null
  nuevaAusencia: Ausencia | null
  calculando: boolean
  error: string | null
  onNota: (n: NotaDatos | null) => void
  onAplicar: () => void
  onDescartar: () => void
  onAusencia: () => void
}

export function Panel(p: Props) {
  const { convenio, propuesta, nuevaAusencia, hoja } = p
  const nota = (r: Regla, titulo?: string) => ({
    onMouseEnter: (e: MouseEvent) => p.onNota(notaDeRegla(e, r, titulo)),
    onMouseMove: (e: MouseEvent) => p.onNota(notaDeRegla(e, r, titulo)),
    onMouseLeave: () => p.onNota(null),
  })
  const dia = (d: number) => {
    const f = new Date(hoja.fechas[d])
    return `${'LMXJVSD'[(f.getDay() + 6) % 7]} ${f.getDate()}`
  }

  if (p.calculando || propuesta) {
    const a = nuevaAusencia!
    return (
      <aside className="panel">
        <header>Cubrir una ausencia</header>
        <section>
          <p>
            <b>{a.persona}</b>, {a.motivo || 'ausencia'} el {dia(hoja.fechas.indexOf(a.fecha))}
            {a.desde != null ? ` de ${a.desde} a ${a.hasta}` : ', todo el día'}. Avisa el {new Date(a.aviso).getDate()}
            {a.imprevista ? ', sin estar prevista.' : '.'}
          </p>
          {p.calculando && <p className="apagado">Buscando quién puede cubrirlo sin saltarse el convenio…</p>}
        </section>
        {propuesta && (
          <>
            <section>
              <h3>Propuesta</h3>
              {propuesta.cambios.length === 0 && propuesta.sin_cubrir.length === 0 && <p>No hace falta tocar nada: la cobertura sigue llegando.</p>}
              {propuesta.cambios.map(c => {
                const ops = propuesta.opciones[c.persona]
                return (
                  <div className="cambio" key={`${c.persona}-${c.dia}`}>
                    <span className="quien">{c.persona}</span>
                    <span className="turno">{dia(c.dia)} · {c.antes ? fmt(c.antes) : 'libre'} → {fmt(c.despues)}</span>
                    {Object.entries(c.horas).map(([clase, h]) => {
                      const op = ops.find(o => o.clase === clase)
                      return (
                        <span className="clase" key={clase} {...(op?.regla ? nota(op.regla) : {})}>
                          +{h} h · {NOMBRE_CLASE[clase as Clase]} {op?.regla && <span className="art">{articulo(op.regla)}</span>}
                        </span>
                      )
                    })}
                  </div>
                )
              })}
              {propuesta.sin_cubrir.length > 0 && (
                <p className="error">
                  Sin cubrir: {propuesta.sin_cubrir.map(s => `${dia(s.dia)} ${s.hora}–${s.hora + 1} (faltan ${s.faltan})`).join(', ')}.
                  Nadie puede hacerlo dentro del convenio con este preaviso.
                </p>
              )}
              <p>
                <span className={`sello ${propuesta.incumplimientos.length ? 'mal' : 'bien'}`}>
                  {propuesta.incumplimientos.length} incumplimientos
                </span>{' '}
                <span className="apagado">según el comprobador</span>
              </p>
              <div className="acciones">
                <button className="boton" onClick={p.onDescartar}>Descartar</button>
                <button className="boton principal" onClick={p.onAplicar} disabled={!propuesta.cuadrante}>Aplicar</button>
              </div>
            </section>
            <section>
              <h3>Quién puede qué</h3>
              <p className="apagado">Con el preaviso que hay. Pasa el ratón por una casilla para ver por qué.</p>
              <table className="quien-puede">
                <thead><tr><th /> {CLASES.map(c => <th key={c} title={NOMBRE_CLASE[c]}>{CORTO[c]}</th>)}</tr></thead>
                <tbody>
                  {hoja.plantilla.map(pers => (
                    <tr key={pers.nombre}>
                      <td>{pers.nombre}</td>
                      {propuesta.opciones[pers.nombre].map(o => (
                        <td key={o.clase} className={o.puede ? 'si' : 'no'}
                          onMouseEnter={e => p.onNota({ x: e.clientX, y: e.clientY, titulo: `${pers.nombre} · ${NOMBRE_CLASE[o.clase]}`, texto: o.motivo + (o.regla ? ` (${articulo(o.regla)})` : '') })}
                          onMouseLeave={() => p.onNota(null)}>
                          {o.puede ? '✓' : '·'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )}
        {p.error && <section><p className="error">{p.error}</p></section>}
      </aside>
    )
  }

  const convenioReglas = convenio.efectivas.filter(r => r.origen === 'convenio')
  const estatuto = convenio.efectivas.filter(r => r.origen === 'estatuto')
  // Un acuerdo por persona y regla, aunque cubra varias ventanas.
  const pactos = [...new Map(p.acuerdos.map(a => [`${a.persona}|${a.tipo}`, a])).values()]
  return (
    <aside className="panel">
      <header>{convenio.nombre} <span className="sello">{convenio.boe}</span></header>
      <section>
        <p>
          <span className={`sello ${p.incumplimientos ? 'mal' : 'bien'}`}>{p.incumplimientos} incumplimientos</span>{' '}
          <span className="apagado">en las 4 semanas{p.pactados ? `, y ${p.pactados} pactados con la persona` : ''}</span>
        </p>
        <p className="apagado">Para cambiar un turno, selecciona la celda y escribe en la barra de fórmulas (7-15, o 22-6 para una noche). Supr la deja libre.</p>
        <p className="apagado">Jornada completa bajo este convenio: {convenio.completa} h a la semana.</p>
        <button className="boton" onClick={p.onAusencia}>Marcar ausencia…</button>{' '}
        <span className="apagado">o clic derecho en un turno</span>
        {p.ausencias.length > 0 && (
          <p style={{ marginTop: 8 }}>Ausencias aplicadas: {p.ausencias.map(a => `${a.persona} (${dia(hoja.fechas.indexOf(a.fecha))})`).join(', ')}</p>
        )}
      </section>
      {p.error && <section><p className="error">{p.error}</p></section>}
      {p.avisos.length > 0 && (
        <section>
          <h3>Última edición</h3>
          <div style={{ display: 'grid', gap: 6 }}>
            {agrupar(p.avisos).map(({ i, n }) => <Incidencia key={`${i.tipo}|${i.persona}`} i={i} n={n} />)}
          </div>
        </section>
      )}
      {pactos.length > 0 && (
        <section>
          <h3>Acuerdos con la plantilla</h3>
          <ul className="acuerdos">
            {pactos.map(a => {
              const r = convenio.efectivas.find(x => x.tipo === a.tipo)
              return (
                <li key={`${a.persona}|${a.tipo}`} {...(r?.cita_pacto ? nota({ ...r, cita: r.cita_pacto }, `${a.persona} · acuerdo individual`) : {})}>
                  <b>{a.persona}</b>: {r ? enunciado(r) : a.tipo} {r && <span className="art">{articulo(r)}</span>}
                </li>
              )
            })}
          </ul>
        </section>
      )}
      <section>
        <h3>Lo que dice el convenio</h3>
        <ul className="reglas">
          {convenioReglas.map((r, i) => (
            <li key={i} {...nota(r)} className={r.estado !== 'aplica' ? 'no-aplica' : ''}>
              <span>{enunciado(r)}</span><span className="art">{articulo(r)}</span>
              {r.pactable !== 'no' && <span className="pacto">Se puede pactar ({r.pactable === 'individual' ? 'con la persona' : 'con la representación'})</span>}
              {r.estado !== 'aplica' && <span className="estado">{r.estado}</span>}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3>Lo que pone el Estatuto</h3>
        <p className="apagado">El convenio no lo regula, así que manda el mínimo legal.</p>
        <ul className="reglas">
          {estatuto.map((r, i) => (
            <li key={i} {...nota(r)} className={`et ${r.estado !== 'aplica' ? 'no-aplica' : ''}`}>
              <span>{enunciado(r)}</span><span className="art">{articulo(r)}</span>
              {r.estado !== 'aplica' && <span className="estado">{r.estado}</span>}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <details>
          <summary>Lo que el convenio dice y aquí no se aplica ({convenio.resto.length})</summary>
          <ul className="reglas">
            {convenio.resto.map((r, i) => (
              <li key={i} {...nota(r)} className="no-aplica">
                <span>{enunciado(r)}</span><span className="art">{articulo(r)}</span>
                <span className="estado">{r.condicion ? `Solo si: ${r.condicion}` : r.tipo === 'otra' ? 'Para revisión: el solver no la aplica' : r.vigente_desde ? `Escalón de ${r.vigente_desde}` : 'Sustituida por otra regla del mismo tipo'}</span>
              </li>
            ))}
          </ul>
        </details>
      </section>
    </aside>
  )
}

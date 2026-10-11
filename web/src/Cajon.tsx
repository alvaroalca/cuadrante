import { articulo } from './api'
import type { Acuerdo, Convenio, Hoja, Incumplimiento, Regla } from './api'
import { enunciado } from './reglas'
import { DIAS, diaSemana } from './Hoja'

export type Pestana = 'problemas' | 'convenio' | 'acuerdos'

function FichaRegla({ r, nota }: { r: Regla; nota?: string }) {
  return (
    <div className={`regla ${r.estado && r.estado !== 'aplica' ? 'no-aplica' : ''}`}>
      <div className="cabeza"><span>{enunciado(r)}</span><span className="art">{articulo(r)}</span></div>
      <q>{r.cita.texto}</q>
      {(nota || r.pactable !== 'no') && (
        <span className="etiqueta">
          {nota ?? `Se puede pactar ${r.pactable === 'individual' ? 'con la persona' : 'con la representación'}`}
        </span>
      )}
    </div>
  )
}

export function Cajon({ pestana, convenio, hoja, incumplimientos, acuerdos, onPestana, onCerrar }: {
  pestana: Pestana
  convenio: Convenio
  hoja: Hoja
  incumplimientos: Incumplimiento[]
  acuerdos: Acuerdo[]
  onPestana: (p: Pestana) => void
  onCerrar: () => void
}) {
  const dia = (d: number) => `${DIAS[diaSemana(hoja.fechas[d])]} ${new Date(hoja.fechas[d]).getDate()}`
  const abiertos = incumplimientos.filter(i => !i.pactado)
  const pactos = [...new Map(acuerdos.map(a => [`${a.persona}|${a.tipo}`, a])).values()]
  return (
    <aside className="cajon" aria-label="Convenio e incumplimientos">
      <header>
        <button className="pestana" aria-pressed={pestana === 'problemas'} onClick={() => onPestana('problemas')}>Incumplimientos ({abiertos.length})</button>
        <button className="pestana" aria-pressed={pestana === 'convenio'} onClick={() => onPestana('convenio')}>Convenio</button>
        <button className="pestana" aria-pressed={pestana === 'acuerdos'} onClick={() => onPestana('acuerdos')}>Acuerdos ({pactos.length})</button>
        <button className="boton cerrar" onClick={onCerrar} aria-label="Cerrar">×</button>
      </header>
      <div className="cuerpo">
        {pestana === 'problemas' && (abiertos.length === 0
          ? <p className="apagado">El cuadrante cumple el convenio y cubre todas las horas.</p>
          : abiertos.map((i, k) => (
            <div key={k} className={`regla`}>
              <div className="cabeza">
                <span>{i.persona ? <b>{i.persona}: </b> : null}{i.mensaje}</span>
                {i.regla && <span className="art">{articulo(i.regla)}</span>}
              </div>
              <span className="etiqueta">{i.dias.slice(0, 7).map(dia).join(', ')}{i.dias.length > 7 ? '…' : ''}</span>
              {i.regla && <q>{i.regla.cita.texto}</q>}
            </div>
          )))}
        {pestana === 'convenio' && (
          <>
            <p className="apagado">{convenio.nombre} ({convenio.boe}). Jornada completa: {convenio.completa} h a la semana.</p>
            <h3>Lo que dice el convenio</h3>
            {convenio.efectivas.filter(r => r.origen === 'convenio').map((r, k) => <FichaRegla key={k} r={r} />)}
            <h3>Lo que pone el Estatuto</h3>
            <p className="apagado">El convenio no lo regula, así que manda el mínimo legal.</p>
            {convenio.efectivas.filter(r => r.origen === 'estatuto').map((r, k) => <FichaRegla key={k} r={r} nota="Mínimo legal: no se puede pactar a la baja (ET 3.5)" />)}
            <h3>En el convenio, pero aquí no se aplica ({convenio.resto.length})</h3>
            {convenio.resto.map((r, k) => (
              <FichaRegla key={k} r={{ ...r, estado: 'no' }} nota={r.condicion ? `Solo si: ${r.condicion}` : r.tipo === 'otra' ? 'Para revisión: el solver no la aplica' : r.vigente_desde ? `Escalón de ${r.vigente_desde}` : 'Sustituida por otra regla del mismo tipo'} />
            ))}
          </>
        )}
        {pestana === 'acuerdos' && (pactos.length === 0
          ? <p className="apagado">Ningún acuerdo individual registrado. Se registran al confirmar un cambio que la persona acepta.</p>
          : pactos.map(a => {
            const r = convenio.efectivas.find(x => x.tipo === a.tipo)
            return r
              ? <FichaRegla key={`${a.persona}|${a.tipo}`} r={{ ...r, cita: r.cita_pacto ?? r.cita }} nota={`Acuerdo de ${a.persona}`} />
              : <p key={`${a.persona}|${a.tipo}`}><b>{a.persona}</b>: {a.mensaje}</p>
          }))}
      </div>
    </aside>
  )
}

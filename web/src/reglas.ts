import type { Regla } from './api'

const h = (v?: number) => `${v ?? '?'} h`
const plazo = (r: Regla) => `${r.valor} ${r.unidad === 'dias' ? (r.valor === 1 ? 'día' : 'días') : r.unidad}`
const n = (v: number | undefined, uno: string, varios: string) => `${v} ${v === 1 ? uno : varios}`

/** Una regla contada como la diría un responsable. */
export function enunciado(r: Regla): string {
  switch (r.tipo) {
    case 'jornada_anual_max': return `Jornada anual: ${h(r.valor)}`
    case 'horas_semana_promedio_max': return `Promedio semanal: ${h(r.valor)}`
    case 'horas_semana_tope': return `Tope en una semana: ${h(r.valor)}`
    case 'horas_dia_max': return `Máximo en un día: ${h(r.valor)}`
    case 'descanso_entre_jornadas_min': return `Entre jornadas: ${h(r.valor)} de descanso`
    case 'descanso_semanal_min':
      return `Descanso semanal: ${r.valor === 1.5 ? 'día y medio' : n(r.valor, 'día', 'días')} seguidos`
        + (r.ventana_dias ? `, acumulable en ${r.ventana_dias} días` : '')
    case 'dias_libres_min_en_ventana': return `${n(r.valor, 'día libre', 'días libres')} en cada ${r.ventana_dias} días`
    case 'dias_consecutivos_max': return `Como mucho ${r.valor} días seguidos`
    case 'fines_semana_libres_min': return `${n(r.valor, 'fin de semana libre', 'fines de semana libres')} ${r.periodo === 'mes' ? 'al mes' : 'al año'}`
    case 'domingos_libres_min':
      return `${n(r.valor, 'domingo libre', 'domingos libres')}`
        + (r.ventana_dias ? ` cada ${r.ventana_dias % 7 === 0 ? n(r.ventana_dias / 7, 'semana', 'semanas') : `${r.ventana_dias} días`}` : '')
    case 'domingos_festivos_trabajo_max': return `Como mucho ${r.valor} domingos y festivos ${r.periodo === 'año' ? 'al año' : ''}`
    case 'descanso_compensatorio_festivo': return `Festivo trabajado: ${n(r.valor, 'día libre', 'días libres')} a cambio`
    case 'horas_noche_promedio_max': return `De noche: ${h(r.valor)} diarias de promedio`
    case 'turno_banda': return `Turno de ${r.turno}: de ${r.desde} a ${r.hasta}`
    case 'pausa_jornada_partida':
      return `Pausa en jornada partida: ${[r.valor && `mín. ${h(r.valor)}`, r.valor_max && `máx. ${h(r.valor_max)}`].filter(Boolean).join(', ')}`
    case 'replanificacion_max_plantilla': return `Cambiar horarios: como mucho al ${r.valor} % de la plantilla`
    case 'preaviso_cambio_min': return `Preaviso de horarios: ${plazo(r)}`
    case 'complementarias_pactadas_max_pct': return `Complementarias pactadas: hasta el ${r.valor} %`
    case 'complementarias_voluntarias_max_pct': return `Complementarias voluntarias: hasta el ${r.valor} %`
    case 'preaviso_complementarias_min': return `Preaviso de complementarias: ${plazo(r)}`
    default: return r.descripcion ?? r.tipo
  }
}

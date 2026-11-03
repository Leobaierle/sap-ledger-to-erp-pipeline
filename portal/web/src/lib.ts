// Formatação, status e acesso à API do portal.

export type StatusKey = 'agendado' | 'andamento' | 'sucesso' | 'pendencias' | 'erro' | 'verificar' | 'sem' | 'naoexec'

export interface Etapa { n: number; nome: string; status: StatusKey; iniciado_em: string | null; terminado_em: string | null; nota: string }
export interface Execucao {
  id: number; data: string; sigla: string; status: StatusKey; periodo_de: string | null; periodo_ate: string | null
  iniciado_em: string | null; terminado_em: string | null; docs_extraidos: number; docs_novos: number; docs_segurados: number
  lancamentos: number; linhas: number; partes: number; debito: number; credito: number; lote: number | null
  avisos: string[]; conferencia: 'gravou' | 'nao' | null; conferencia_em: string | null
  tem_planilha: boolean; tem_razao: boolean; tem_balancete: boolean; observacao: string; etapas?: Etapa[]
}
export interface LogLinha { quando: string; nivel: 'info' | 'aviso' | 'erro'; etapa: string; mensagem: string }
export interface Print { id: number; quando: string; arquivo: string; legenda: string }
export interface Resumo {
  config: { ambiente: string; horario: string | null }
  hoje: string
  ultima: Execucao | null
  mes: { id: number; data: string; status: StatusKey; docs_novos: number; lancamentos: number; lote: number | null }[]
  pendencias: { contas: number; segurados: number }
  verificar: { id: number; data: string; lote: number | null }[]
  alterados: number
  pedido: Pedido | null
}
export interface Pedido {
  id: number; pedido_por: string; criado_em: string; status: 'fila' | 'rodando' | 'feito' | 'erro'
  iniciado_em: string | null; terminado_em: string | null; execucao_id: number | null; mensagem: string
  de: string | null; ate: string | null
}
export interface PendConta { codigo_sap: string; nome_sap: string; docs: number; linhas: number; debito: number; credito: number; historico_exemplo: string; salvo: { codigo: string; nome: string } | null }
export interface Segurado { doc: string; data_lancamento: string; valor: number; desde: string; liberado: boolean; contas: { conta: string; nome: string }[] }
export interface Pendencias { contas: PendConta[]; segurados: Segurado[]; codigo_livre: number }
export interface Alterado { doc: string; data_lancamento: string; lote: number; campo: string; antes: string; depois: string; detectado_em: string }
export interface LinhaPlano { conta_sap: string; conta_erp: string; nome_conta: string; sintetica_erp: string; conta_referencial: string }
export interface LinhaCC { centro_custo_sap: string; centro_custo_resumido: string; centro_custo_erp: string }

export async function api<T>(caminho: string, opcoes?: { metodo?: string; corpo?: unknown }): Promise<T> {
  const r = await fetch(caminho, {
    method: opcoes?.metodo || 'GET',
    credentials: 'include',
    headers: opcoes?.corpo !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: opcoes?.corpo !== undefined ? JSON.stringify(opcoes.corpo) : undefined,
  })
  const dados = await r.json().catch(() => ({}))
  if (r.status === 401 || r.status === 403) window.dispatchEvent(new Event('icm-sessao'))
  if (!r.ok) throw new Error((dados as { erro?: string }).erro || `Erro ${r.status}`)
  return dados as T
}

// — formatação —
const TZ = 'America/Sao_Paulo'
const nf = new Intl.NumberFormat('pt-BR')
const cf = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export const fInt = (n: number) => nf.format(n)
export const fBRL = (n: number) => 'R$ ' + cf.format(n)
export const pl = (n: number, s: string, p: string) => fInt(n) + ' ' + (n === 1 ? s : p)
export const pad = (n: number) => String(n).padStart(2, '0')
export const fDate = (iso: string) => iso.slice(0, 10).split('-').reverse().join('/')
const WD = ['domingo', 'segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado']
export const dObj = (iso: string) => { const [y, m, d] = iso.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d) }
export const isoOf = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
export const addDays = (iso: string, n: number) => { const d = dObj(iso); d.setDate(d.getDate() + n); return isoOf(d) }
export const wd = (iso: string) => WD[dObj(iso).getDay()]
export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
export const fDur = (sec: number) => {
  sec = Math.round(sec); const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60
  if (h) return `${h} h ${pad(m)} min`; if (m) return `${m} min ${pad(s)} s`; return `${s} s`
}
const hf = new Intl.DateTimeFormat('pt-BR', { timeZone: TZ, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
const dhf = new Intl.DateTimeFormat('pt-BR', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
export const fHora = (ts: string | null) => (ts ? hf.format(new Date(ts)) : '—')
export const fDataHora = (ts: string | null) => (ts ? dhf.format(new Date(ts)).replace(', ', ' às ') : '—')
export const segundos = (a: string | null, b: string | null) => (a && b ? (new Date(b).getTime() - new Date(a).getTime()) / 1000 : null)
const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
export const nomeMes = (ym: string) => { const [y, m] = ym.split('-').map(Number); return `${MESES[m - 1]}/${y}` }

// — status —
type Variante = 'neutral' | 'info' | 'ok' | 'warn' | 'err' | 'check' | 'none'
export const ST: Record<StatusKey, { label: string; v: Variante }> = {
  agendado: { label: 'Agendado', v: 'neutral' },
  andamento: { label: 'Em andamento', v: 'info' },
  sucesso: { label: 'Sucesso', v: 'ok' },
  pendencias: { label: 'Sucesso com pendências', v: 'warn' },
  erro: { label: 'Erro', v: 'err' },
  verificar: { label: 'Verificar', v: 'check' },
  sem: { label: 'Sem novidades', v: 'none' },
  naoexec: { label: 'Não executada', v: 'none' },
}
const FG: Record<Variante, string> = { neutral: '#fff', info: '#fff', ok: '#fff', warn: '#201e1d', err: '#fff', check: '#fff', none: '#201e1d' }
export const cores = (k: StatusKey) => {
  const v = ST[k].v
  return { color: `var(--st-${v})`, bg: `var(--st-${v}-bg)`, solid: `var(--st-${v}-solid)`, fg: FG[v] }
}

// — próxima execução (horário em robo_config; null = a definir) —
export function proximaExecucao(horario: string | null, agora = new Date()): string | null {
  if (!horario) return null
  const [h, m] = horario.split(':').map(Number)
  const hoje = isoOf(agora)
  const passou = agora.getHours() * 60 + agora.getMinutes() >= h * 60 + m
  return passou ? addDays(hoje, 1) : hoje
}

export const fHoraCurta = (ts: string | null) => fHora(ts).slice(0, 5)
/** "16:15:47 → 16:17:19 · 1 min 32 s" (linha curta das etapas). */
export function linhaEtapa(e: Etapa): string {
  if (!e.iniciado_em) return e.status === 'agendado' ? 'Aguardando a etapa anterior' : 'Não executada'
  if (!e.terminado_em) return `Início ${fHora(e.iniciado_em)} · em andamento`
  return `${fHora(e.iniciado_em)} → ${fHora(e.terminado_em)} · ${fDur(segundos(e.iniciado_em, e.terminado_em)!)}`
}
export const periodoLabel = (e: Execucao) =>
  e.periodo_de && e.periodo_ate ? `${fDate(e.periodo_de)} a ${fDate(e.periodo_ate)}` : 'nenhum dia do mês ainda (1º dia)'
export const duracao = (e: Execucao) => segundos(e.iniciado_em, e.terminado_em)

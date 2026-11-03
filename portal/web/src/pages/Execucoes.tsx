import { useEffect, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { ir, type Contexto } from '../App'
import { api, cap, cores, duracao, fDate, fDur, fInt, nomeMes, pl, ST, wd, type Execucao, type StatusKey } from '../lib'
import { Carregando, Status, StatusIcone } from '../ui'

export default function Execucoes({ ctx }: { ctx: Contexto }) {
  const [mes, setMes] = useState(ctx.resumo.hoje.slice(0, 7))
  const [status, setStatus] = useState<'all' | StatusKey>('all')
  const [dados, setDados] = useState<{ execucoes: Execucao[]; meses: string[] } | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  useEffect(() => {
    api<{ execucoes: Execucao[]; meses: string[] }>(`/api/execucoes?mes=${mes}&status=${status}`)
      .then(d => { setDados(d); setErro(null) }).catch(e => setErro(e.message))
  }, [mes, status])

  const horario = ctx.resumo.config.horario
  const agendada = ctx.proxima && (mes === 'all' || ctx.proxima.slice(0, 7) === mes) && (status === 'all' || status === 'agendado') ? ctx.proxima : null
  const lista = dados?.execucoes || []
  const importadas = lista.filter(r => r.lote && r.status !== 'erro')
  const meses = Array.from(new Set([ctx.resumo.hoje.slice(0, 7), ...(dados?.meses || [])])).sort().reverse()
  const chips: ('all' | StatusKey)[] = ['all', 'sucesso', 'pendencias', 'erro', 'verificar', 'sem']

  return (
    <div className="pilha-20">
      <div className="cab">
        <h1>Execuções</h1>
        <p>Uma linha por noite. Clique numa execução para ver etapas, log, avisos e arquivos.</p>
      </div>
      <div className="filtros">
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <span className="mute">Mês</span>
          <select className="input" value={mes} onChange={e => setMes(e.target.value)} style={{ width: 'auto', minWidth: 170 }}>
            {meses.map(m => <option key={m} value={m}>{cap(nomeMes(m))}</option>)}
            <option value="all">Todos os meses</option>
          </select>
        </label>
        <div role="group" aria-label="Filtrar por status" style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {chips.map(k => (
            <button key={k} className="chip" aria-pressed={status === k} onClick={() => setStatus(k)}>
              {k !== 'all' && <span className="chip-ic" style={{ color: cores(k).color, display: 'flex' }}><StatusIcone k={k} /></span>}
              {k === 'all' ? 'Todos' : k === 'pendencias' ? 'Com pendências' : ST[k].label}
            </button>
          ))}
        </div>
        <span className="mute" style={{ marginLeft: 'auto', fontSize: 13 }}>
          {pl(lista.length, 'execução', 'execuções')}{agendada ? ' + 1 agendada' : ''}
        </span>
      </div>
      {erro && <div className="erro-pagina">{erro}</div>}
      {!dados ? <Carregando /> : (
        <div className="tabela-caixa">
          <table className="table densa" style={{ minWidth: 1080 }}>
            <thead>
              <tr>
                <th style={{ paddingLeft: 16 }}>Data</th><th>Ambiente</th><th>Status</th>
                <th className="dir">Docs extraídos</th><th className="dir">Docs novos</th><th className="dir">Docs segurados</th>
                <th className="dir">Lançamentos</th><th className="dir">Linhas</th><th>Lote</th><th className="dir">Duração</th><th aria-label="Abrir" />
              </tr>
            </thead>
            <tbody>
              {agendada && (
                <tr>
                  <td style={{ paddingLeft: 16 }}><div>{fDate(agendada)}</div><div className="data-sub">{cap(wd(agendada))}</div></td>
                  <td><span className="tag tag-neutral">{ctx.resumo.config.ambiente}</span></td>
                  <td><Status k="agendado" /></td>
                  <td className="dir">—</td><td className="dir">—</td><td className="dir">{fInt(ctx.resumo.pendencias.segurados)}</td>
                  <td className="dir">—</td><td className="dir">—</td><td>—</td><td className="dir" style={{ whiteSpace: 'nowrap' }}>Início às {horario}</td><td />
                </tr>
              )}
              {lista.map(r => {
                const d = duracao(r)
                return (
                  <tr key={r.id} className="clicavel" tabIndex={0} onClick={() => ir('detalhe', r.id)} onKeyDown={e => { if (e.key === 'Enter') ir('detalhe', r.id) }}>
                    <td style={{ paddingLeft: 16 }}><div>{fDate(r.data)}</div><div className="data-sub">{cap(wd(r.data))}</div></td>
                    <td><span className="tag tag-neutral">{r.sigla}</span></td>
                    <td><Status k={r.status} /></td>
                    <td className="dir">{fInt(r.docs_extraidos)}</td>
                    <td className="dir">{fInt(r.docs_novos)}</td>
                    <td className="dir">{fInt(r.docs_segurados)}</td>
                    <td className="dir">{fInt(r.lancamentos)}</td>
                    <td className="dir">{fInt(r.linhas)}</td>
                    <td>{r.lote ? String(r.lote) + (r.conferencia === 'nao' ? ' (não gravado)' : '') : '—'}</td>
                    <td className="dir" style={{ whiteSpace: 'nowrap' }}>{d != null ? fDur(d) : '—'}</td>
                    <td className="mute"><ChevronRight size={14} /></td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={4} style={{ paddingLeft: 16 }}>Total · {pl(importadas.length, 'lote importado', 'lotes importados')}</td>
                <td className="dir">{fInt(importadas.reduce((a, r) => a + r.docs_novos, 0))}</td>
                <td />
                <td className="dir">{fInt(importadas.reduce((a, r) => a + r.lancamentos, 0))}</td>
                <td className="dir">{fInt(importadas.reduce((a, r) => a + r.linhas, 0))}</td>
                <td colSpan={3} />
              </tr>
            </tfoot>
          </table>
          {!lista.length && !agendada && <div className="vazio">Nenhuma execução com esse filtro.</div>}
        </div>
      )}
    </div>
  )
}

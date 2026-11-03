import { useEffect, useState } from 'react'
import { ArrowLeft, Check, CircleHelp, Download, FileSpreadsheet, Search, TriangleAlert } from 'lucide-react'
import { ir, type Contexto } from '../App'
import { api, cap, cores, duracao, fBRL, fDate, fDur, fHora, fInt, periodoLabel, pl, segundos, wd, type Execucao, type LogLinha, type Print } from '../lib'
import { Carregando, Status, StatusIcone, useToast } from '../ui'

type Det = Execucao & { log: LogLinha[]; prints: Print[] }
const NIVEL = { info: ['INFO', 'var(--mute)', 'transparent'], aviso: ['AVISO', 'var(--st-warn)', 'transparent'], erro: ['ERRO', 'var(--perigo-700)', 'var(--st-err-bg)'] } as const

export default function Detalhe({ ctx, id }: { ctx: Contexto; id: number }) {
  const toast = useToast()
  const [d, setD] = useState<Det | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [nivel, setNivel] = useState<'all' | 'info' | 'aviso' | 'erro'>('all')
  const [q, setQ] = useState('')
  const carregar = () => api<Det>(`/api/execucoes/${id}`).then(setD).catch(e => setErro(e.message))
  useEffect(() => { carregar() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (erro) return <div className="erro-pagina">{erro}</div>
  if (!d) return <Carregando />

  const conferir = (resultado: 'gravou' | 'nao' | null) =>
    api(`/api/execucoes/${id}/conferencia`, { metodo: 'POST', corpo: { resultado } }).then(() => {
      if (resultado === 'gravou') toast('Conferência registrada', `Lote ${d.lote} gravou na ERP · os documentos não serão importados de novo.`)
      if (resultado === 'nao') toast('Conferência registrada', `Os documentos do lote ${d.lote} entram de novo na próxima execução (${ctx.proximaLabel}).`)
      carregar(); ctx.recarregar()
    }).catch(e => toast('Não foi possível registrar', e.message, 'erro'))

  const qq = q.trim().toLowerCase()
  const contagem = { info: 0, aviso: 0, erro: 0 }
  d.log.forEach(l => contagem[l.nivel]++)
  const log = d.log.filter(l => (nivel === 'all' || l.nivel === nivel) && (!qq || (l.mensagem + ' ' + l.etapa).toLowerCase().includes(qq)))
  const avisos = (d.docs_segurados ? [`${pl(d.docs_segurados, 'documento segurado', 'documentos segurados')} por conta SAP sem correspondência na ERP`] : []).concat(d.avisos)
  const parou = d.etapas?.find(e => e.status === 'erro')
  const dur = duracao(d)
  const etapas = d.etapas || []

  return (
    <div className="pilha-20">
      <button className="btn btn-ghost" onClick={() => ir('execucoes')} style={{ alignSelf: 'flex-start', paddingLeft: 0 }}><ArrowLeft size={16} />Voltar para Execuções</button>
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'flex-end', gap: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <h1 style={{ fontSize: 24, letterSpacing: '-0.02em' }}>Execução de {fDate(d.data)}</h1>
            <Status k={d.status} grande />
            <span className="tag tag-neutral">{d.sigla}</span>
          </div>
          <p className="mute" style={{ margin: 0 }}>{cap(wd(d.data))} · período {periodoLabel(d)} · {d.lote ? 'lote ' + d.lote : 'sem lote'}{dur != null ? ` · duração total ${fDur(dur)}` : ''}</p>
          {d.observacao && <p className="mute" style={{ margin: 0, fontSize: 13 }}>{d.observacao}</p>}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <a className="btn btn-secondary" aria-disabled={!d.tem_planilha} href={d.tem_planilha ? `/api/execucoes/${id}/arquivo/planilha` : undefined}
            style={d.tem_planilha ? undefined : { opacity: 0.45, cursor: 'not-allowed' }} title={d.tem_planilha ? undefined : 'Sem planilha nesta execução'}>
            <FileSpreadsheet size={16} />Baixar planilha gerada</a>
          <a className="btn btn-secondary" aria-disabled={!d.tem_razao} href={d.tem_razao ? `/api/execucoes/${id}/arquivo/razao` : undefined}
            style={d.tem_razao ? undefined : { opacity: 0.45, cursor: 'not-allowed' }} title={d.tem_razao ? undefined : 'Sem Razão nesta execução'}>
            <Download size={16} />Baixar Razão extraído</a>
          <a className="btn btn-secondary" aria-disabled={!d.tem_balancete} href={d.tem_balancete ? `/api/execucoes/${id}/arquivo/balancete` : undefined}
            style={d.tem_balancete ? undefined : { opacity: 0.45, cursor: 'not-allowed' }} title={d.tem_balancete ? undefined : 'Sem balancete nesta execução'}>
            <Download size={16} />Baixar balancete</a>
        </div>
      </div>

      {d.status === 'verificar' && !d.conferencia && (
        <div role="alert" className="aviso-verificar">
          <CircleHelp size={22} />
          <span style={{ fontWeight: 700, fontSize: 15 }}>Confira na ERP se o lote {d.lote} foi gravado</span>
          <span style={{ fontSize: 14, maxWidth: 760, textWrap: 'pretty' }}>A importação foi até o fim, mas a ERP não mostrou a tela de confirmação. O lote pode ou não ter sido gravado. Abra a ERP, procure o lote {d.lote} na empresa {d.sigla} e registre o que encontrou — se não gravou, os documentos entram de novo na próxima noite.</span>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
            <button className="btn btn-primary" onClick={() => conferir('gravou')}><Check size={16} />Confirmei: gravou na ERP</button>
            <button className="btn btn-secondary" onClick={() => conferir('nao')} style={{ background: 'var(--color-bg)' }}>Confirmei: não gravou (pode repetir)</button>
          </div>
        </div>
      )}
      {d.conferencia && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', background: 'var(--color-surface)', fontSize: 14 }}>
          <Check size={16} />
          <span>{d.conferencia === 'gravou' ? `Conferência registrada: o lote ${d.lote} gravou na ERP.` : `Conferência registrada: o lote ${d.lote} não gravou — os documentos entram de novo na próxima execução.`}</span>
          <button className="btn btn-ghost" onClick={() => conferir(null)} style={{ marginLeft: 'auto' }}>Desfazer</button>
        </div>
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
        <section aria-label="Linha do tempo" className="superficie" style={{ flex: '3 1 520px' }}>
          <h2>Linha do tempo das etapas</h2>
          <ol className="timeline">
            {etapas.map((s, i) => {
              const c = cores(s.status); const sd = segundos(s.iniciado_em, s.terminado_em)
              return (
                <li key={s.n}>
                  <div className="marco">
                    <span style={{ background: c.bg, color: c.color }}><StatusIcone k={s.status} size={18} /></span>
                    <span className="fio" style={{ visibility: i === etapas.length - 1 ? 'hidden' : 'visible' }} />
                  </div>
                  <div className="conteudo">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>Etapa {s.n} · {s.nome}</span>
                      <Status k={s.status} />
                    </div>
                    <div className="num" style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 18px', fontSize: 13 }}>
                      <span><span className="mute">Início</span> {fHora(s.iniciado_em)}</span>
                      <span><span className="mute">Fim</span> {fHora(s.terminado_em)}</span>
                      <span><span className="mute">Duração</span> {sd != null ? fDur(sd) : s.status === 'andamento' ? 'em andamento' : '—'}</span>
                    </div>
                    {s.nota && <span className="mute" style={{ fontSize: 13 }}>{s.nota}</span>}
                  </div>
                </li>
              )
            })}
          </ol>
        </section>
        <div style={{ flex: '2 1 320px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <section aria-label="Totais" className="superficie" style={{ gap: 12 }}>
            <h2>Totais</h2>
            <dl className="dl-totais">
              <dt>Débito</dt><dd>{fBRL(d.debito)}</dd>
              <dt>Crédito</dt><dd>{fBRL(d.credito)}</dd>
              <dt>Lançamentos</dt><dd>{fInt(d.lancamentos)}</dd>
              <dt>Linhas</dt><dd>{fInt(d.linhas)}</dd>
              <dt>Partes</dt><dd>{pl(d.partes, 'arquivo', 'arquivos')}</dd>
            </dl>
            {d.linhas > 0 && d.debito === d.credito && <span className="ok-chip" style={{ alignSelf: 'flex-start' }}><Check size={16} />Débito = Crédito</span>}
            {!d.lote && d.debito > 0 && <span className="mute" style={{ fontSize: 12 }}>Débito e crédito do Razão extraído; nenhum lote foi gravado nesta execução.</span>}
          </section>
          <section aria-label="Avisos da conversão" className="superficie" style={{ gap: 12 }}>
            <h2>Avisos da conversão</h2>
            {avisos.length ? (
              <ul className="lista-avisos">{avisos.map((a, i) => <li key={i}><TriangleAlert size={16} /><span>{a}</span></li>)}</ul>
            ) : (
              <p className="mute" style={{ margin: 0, fontSize: 13 }}>
                {d.status === 'sem' ? 'Nenhum documento novo para converter.' : d.status === 'andamento' ? 'A conversão ainda está rodando.' : parou?.n === 1 ? 'A conversão não rodou nesta noite.' : 'Nenhum aviso na conversão.'}
              </p>
            )}
          </section>
        </div>
      </div>

      <section aria-label="Log" className="superficie" style={{ gap: 14 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between' }}>
          <h2>Log da execução</h2>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <div role="group" aria-label="Nível" className="seg">
              {([['all', `Todas · ${pl(d.log.length, 'linha', 'linhas')}`], ['info', `${fInt(contagem.info)} info`], ['aviso', pl(contagem.aviso, 'aviso', 'avisos')], ['erro', pl(contagem.erro, 'erro', 'erros')]] as const)
                .map(([k, label]) => <button key={k} aria-pressed={nivel === k} onClick={() => setNivel(k)}>{label}</button>)}
            </div>
            <div className="busca" style={{ width: 260, maxWidth: '100%' }}>
              <Search size={16} />
              <input className="input" type="search" placeholder="Buscar no log" aria-label="Buscar no log" value={q} onChange={e => setQ(e.target.value)} style={{ background: 'var(--color-bg)' }} />
            </div>
          </div>
        </div>
        <div className="log">
          {log.map((l, i) => {
            const [rot, cor, fundo] = NIVEL[l.nivel]
            return (
              <div key={i} className="log-linha" style={{ background: fundo }}>
                <span className="mute">{fHora(l.quando)}</span>
                <span className="log-nivel" style={{ color: cor }}>{rot}</span>
                <span className="log-msg"><span style={{ fontWeight: 600 }}>{l.etapa}</span> — {l.mensagem}</span>
              </div>
            )
          })}
          {!log.length && <div style={{ padding: '24px 12px' }} className="mute">Nenhuma linha do log corresponde ao filtro.</div>}
        </div>
        <span className="mute" style={{ fontSize: 12 }}>Mostrando {pl(log.length, 'linha', 'linhas')} de {fInt(d.log.length)}</span>
      </section>

      {d.prints.length > 0 && (
        <section aria-label="Prints de tela" className="superficie" style={{ gap: 14 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <h2>Prints de tela do robô</h2>
            <span className="mute" style={{ fontSize: 13 }}>{pl(d.prints.length, 'print salvo', 'prints salvos')} pelo robô durante a execução</span>
          </div>
          <div className="prints">
            {d.prints.map(p => (
              <figure key={p.id}>
                <a href={`/api/prints/${p.id}`} target="_blank" rel="noreferrer"><img src={`/api/prints/${p.id}`} alt={p.legenda || p.arquivo} /></a>
                <figcaption style={{ fontSize: 12 }}><strong>{fHora(p.quando)}</strong> · {p.legenda || p.arquivo}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

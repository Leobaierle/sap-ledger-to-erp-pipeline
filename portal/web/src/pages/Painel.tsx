import { useEffect, useState, type CSSProperties } from 'react'
import { ArrowRight, CalendarClock, Check, CircleHelp, ClipboardList, FileDiff, Info, Lock, Play, TriangleAlert, type LucideIcon } from 'lucide-react'
import { ir, type Contexto } from '../App'
import { api, cap, cores, dObj, duracao, fBRL, fDate, fDur, fHoraCurta, fInt, isoOf, linhaEtapa, nomeMes, pad, periodoLabel, pl, ST, wd, type StatusKey } from '../lib'
import { Dialogo, Status, StatusIcone, useToast } from '../ui'

export default function Painel({ ctx }: { ctx: Contexto }) {
  const { resumo, proxima } = ctx
  const u = resumo.ultima
  const horario = resumo.config.horario
  const p = resumo.pendencias
  const toast = useToast()
  const [confirmar, setConfirmar] = useState(false)
  const [ciente, setCiente] = useState(false)
  const [pedindo, setPedindo] = useState(false)
  const [erroPedido, setErroPedido] = useState<string | null>(null)
  const ped = resumo.pedido

  // período do "Executar agora": uma competência (mês corrente ou os 2 anteriores), de/até dentro dela, até hoje
  const competencias = [0, 1, 2].map(n => { const d = dObj(resumo.hoje.slice(0, 7) + '-01'); d.setMonth(d.getMonth() - n); return isoOf(d).slice(0, 7) })
  const fimComp = (ym: string) => { const d = dObj(ym + '-01'); const f = isoOf(new Date(d.getFullYear(), d.getMonth() + 1, 0)); return f < resumo.hoje ? f : resumo.hoje }
  const [comp, setComp] = useState(competencias[0])
  const [de, setDe] = useState('')
  const [ate, setAte] = useState('')
  const escolherComp = (ym: string) => { setComp(ym); setDe(ym + '-01'); setAte(fimComp(ym)); setErroPedido(null) }
  const periodoOk = !!de && !!ate && de <= ate && de.slice(0, 7) === comp && ate.slice(0, 7) === comp && ate <= resumo.hoje
  const periodoPed = ped?.de && ped?.ate ? ` · período ${fDate(ped.de)} a ${fDate(ped.ate)}` : ''
  const ocupado = ped?.status === 'fila' || ped?.status === 'rodando' || u?.status === 'andamento'

  // enquanto houver pedido aberto ou execução em andamento, o painel se atualiza sozinho
  useEffect(() => {
    if (!ocupado) return
    const t = setInterval(ctx.recarregar, 15000)
    return () => clearInterval(t)
  }, [ocupado, ctx.recarregar])

  const executar = () => {
    setPedindo(true); setErroPedido(null)
    api('/api/executar', { metodo: 'POST', corpo: { de, ate } })
      .then(() => { setConfirmar(false); toast('Execução pedida', 'O robô começa em até 1 minuto.'); ctx.recarregar() })
      .catch(e => setErroPedido(e.message))
      .finally(() => setPedindo(false))
  }

  const A = (n: number, label: string, dica: string, I: LucideIcon, onClick: () => void, info?: boolean) => (
    <button key={label} className="alerta" onClick={onClick}>
      <span className="alerta-topo">
        <span className="alerta-icone" style={n ? (info ? { background: 'var(--color-neutral-100)', color: 'var(--color-muted)' } : { background: 'var(--perigo-100)', color: 'var(--perigo-700)' }) : { background: 'var(--st-ok-bg)', color: 'var(--st-ok)' }}><I size={18} /></span>
        <ArrowRight size={16} className="mute" />
      </span>
      <span className="alerta-num"><b>{fInt(n)}</b><span>{label}</span></span>
      <span className="mute" style={{ fontSize: 12 }}>{dica}</span>
    </button>
  )
  const verif = resumo.verificar

  // calendário do mês corrente
  const ym = resumo.hoje.slice(0, 7)
  const ini = dObj(ym + '-01')
  const diasNoMes = new Date(ini.getFullYear(), ini.getMonth() + 1, 0).getDate()
  const celulas = []
  for (let i = 0; i < ini.getDay(); i++) celulas.push(<span key={'v' + i} />)
  for (let d = 1; d <= diasNoMes; d++) {
    const iso = `${ym}-${pad(d)}`
    const r = resumo.mes.find(x => x.data === iso)
    if (r) {
      const c = cores(r.status)
      celulas.push(<button key={iso} className="cal-dia" title={`${fDate(iso)} · ${ST[r.status].label}`} aria-label={`${fDate(iso)} · ${ST[r.status].label}`}
        onClick={() => ir('detalhe', r.id)} style={{ border: 0, background: c.solid, color: c.fg, cursor: 'pointer' }}>{d}</button>)
    } else if (iso === proxima) {
      celulas.push(<span key={iso} className="cal-dia" title={`${fDate(iso)} · Agendado às ${horario}`} style={{ border: '2px solid var(--st-neutral-solid)' }}>{d}</span>)
    } else {
      celulas.push(<span key={iso} className="cal-dia" title={`${fDate(iso)} · sem execução`} style={{ border: '1px dashed var(--color-divider)', color: 'var(--mute)' }}>{d}</span>)
    }
  }
  const importadas = resumo.mes.filter(r => r.lote && r.status !== 'erro')
  const legenda: StatusKey[] = ['sucesso', 'pendencias', 'erro', 'verificar', 'sem']

  return (
    <div className="pilha">
      <div className="cab" style={{ display: 'flex', flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1>Painel</h1>
          <p>O robô extrai o Razão da ACME no SAP toda noite e importa os documentos novos na ERP.</p>
        </div>
        <button className="btn btn-primary" onClick={() => { escolherComp(competencias[0]); setCiente(false); setConfirmar(true) }} disabled={ocupado}
          title={ocupado ? 'Já existe uma execução pedida ou em andamento' : undefined}>
          <Play size={16} />Executar agora
        </button>
      </div>

      {ped && (
        <div className="caixa-info" role="status"><Info size={18} /><span>{
          ped.status === 'fila' ? `Execução pedida por ${ped.pedido_por} às ${fHoraCurta(ped.criado_em)}${periodoPed} · começa em até 1 minuto.`
            : ped.status === 'rodando' ? `Executando agora (pedido por ${ped.pedido_por} às ${fHoraCurta(ped.criado_em)}${periodoPed}). Acompanhe as etapas abaixo.`
              : ped.status === 'feito' ? `A execução pedida por ${ped.pedido_por} às ${fHoraCurta(ped.criado_em)} terminou.`
                : `A execução pedida por ${ped.pedido_por} às ${fHoraCurta(ped.criado_em)} não terminou bem: ${ped.mensagem}`
        }</span>{ped.execucao_id && (ped.status === 'feito' || ped.status === 'erro') && (
          <button className="btn btn-secondary" onClick={() => ir('detalhe', ped.execucao_id!)} style={{ marginLeft: 'auto' }}>Ver execução<ArrowRight size={16} /></button>
        )}</div>
      )}

      {confirmar && (
        <Dialogo titulo="Executar a importação agora?" okLabel={pedindo ? 'Pedindo…' : 'Executar e gravar na ERP'} ocupado={pedindo || !ciente || !periodoOk} erro={erroPedido}
          onOk={executar} onCancelar={() => setConfirmar(false)}
          corpo={`O robô extrai o Razão e o balancete do SAP no período escolhido e importa na ERP (${resumo.config.ambiente}) só os documentos que ainda não foram importados. Leva uns 15 minutos. Lançamentos feitos no SAP durante a execução entram na próxima.`}>
          <div className="field">
            <label htmlFor="exec-comp">Competência</label>
            <select id="exec-comp" className="input" value={comp} onChange={e => escolherComp(e.target.value)} style={{ background: 'var(--color-surface)' }}>
              {competencias.map(ym => <option key={ym} value={ym}>{cap(nomeMes(ym))}</option>)}
            </select>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
            <div className="field">
              <label htmlFor="exec-de">De</label>
              <input id="exec-de" className="input" type="date" value={de} min={comp + '-01'} max={fimComp(comp)}
                onChange={e => { setDe(e.target.value); setErroPedido(null) }} style={{ background: 'var(--color-surface)' }} />
            </div>
            <div className="field">
              <label htmlFor="exec-ate">Até</label>
              <input id="exec-ate" className="input" type="date" value={ate} min={comp + '-01'} max={fimComp(comp)}
                onChange={e => { setAte(e.target.value); setErroPedido(null) }} style={{ background: 'var(--color-surface)' }} />
            </div>
          </div>
          {!periodoOk && de && ate && <span className="erro-campo">O período tem que estar dentro da competência, com a data inicial antes da final e até hoje.</span>}
          <div className="caixa-info" style={{ background: 'var(--perigo-100)', color: 'var(--perigo-700)' }}>
            <TriangleAlert size={18} /><span>Atenção: isto <b>grava um lote de verdade na ERP</b>. Um lote gravado não se desfaz pelo robô — só excluindo à mão na ERP.</span>
          </div>
          <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 14, cursor: 'pointer' }}>
            <input type="checkbox" checked={ciente} onChange={e => setCiente(e.target.checked)} style={{ marginTop: 3 }} />
            <span>Entendo que a importação vai ser gravada na ERP agora.</span>
          </label>
        </Dialogo>
      )}

      <div className="linha-flex">
        <section aria-label="Última execução" className="superficie" style={{ flex: '2 1 560px', gap: 18 }}>
          {u ? <UltimaExecucao /> : (
            <>
              <span className="kicker">Última execução</span>
              <div className="caixa-info"><Info size={18} /><span>O robô ainda não rodou. A primeira execução aparece aqui.</span></div>
            </>
          )}
        </section>

        <section aria-label="Próxima execução" className="superficie" style={{ flex: '1 1 280px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span className="kicker">Próxima execução</span>
            <CalendarClock size={20} style={{ color: 'var(--color-accent-strong)' }} />
          </div>
          {proxima ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <span className="prox-data">{fDate(proxima)}</span>
              <span style={{ fontSize: 16, fontWeight: 600 }}>{cap(wd(proxima))} às {horario}</span>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <span className="prox-data">A definir</span>
              <span className="mute" style={{ fontSize: 13 }}>O horário da execução noturna ainda não foi definido.</span>
            </div>
          )}
          <dl className="dl-prox">
            <dt>Período</dt><dd>{proxima ? (proxima.slice(8) === '01' ? 'nenhum dia do mês ainda (1º dia)' : `01/${proxima.slice(5, 7)}/${proxima.slice(0, 4)} até a véspera`) : 'do dia 1 do mês até a véspera'}</dd>
            <dt>Destino</dt><dd>ERP · {resumo.config.ambiente} (ACME)</dd>
            <dt>Aguardando</dt><dd>{p.segurados ? pl(p.segurados, 'documento segurado esperando conta', 'documentos segurados esperando conta') : 'Nenhum documento segurado'}</dd>
          </dl>
          <button className="btn btn-secondary" onClick={() => ir('pendencias')} style={{ marginTop: 'auto', justifyContent: 'flex-start' }}>
            {proxima ? `Resolver pendências antes das ${horario}` : 'Resolver pendências'}<ArrowRight size={16} />
          </button>
        </section>
      </div>

      <section aria-label="Alertas" className="alertas">
        {A(p.contas, p.contas === 1 ? 'conta pendente de preenchimento' : 'contas pendentes de preenchimento',
          p.contas ? 'Contas SAP sem conta ERP · bloqueiam documentos' : 'Todas as contas têm correspondência', ClipboardList, () => ir('pendencias'))}
        {A(p.segurados, p.segurados === 1 ? 'documento segurado' : 'documentos segurados',
          p.segurados ? 'Entram na próxima noite depois de preenchida a conta' : 'Nenhum documento esperando', Lock, () => ir('pendencias'))}
        {A(verif.length, verif.length === 1 ? 'lote para verificar na ERP' : 'lotes para verificar na ERP',
          verif.length ? `Lote ${verif.map(v => v.lote).join(', ')} · precisa de conferência humana` : 'Nenhum lote esperando conferência', CircleHelp,
          () => verif.length === 1 ? ir('detalhe', verif[0].id) : ir('execucoes'))}
        {A(resumo.alterados, resumo.alterados === 1 ? 'documento alterado no SAP após importação' : 'documentos alterados no SAP após importação',
          'Informativo · o robô não reimporta', FileDiff, () => ir('alterados'), true)}
      </section>

      <section aria-label="Resumo do mês" className="superficie">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
          <h2 style={{ fontSize: 16 }}>Resumo de {nomeMes(ym)}</h2>
          <span className="mute" style={{ fontSize: 13 }}>Clique numa noite para abrir a execução</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px 40px' }}>
          <div className="metricas" style={{ flex: '1 1 300px', alignContent: 'start', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
            <div className="metrica" style={{ paddingBottom: 12 }}><b>{fInt(importadas.reduce((a, r) => a + r.docs_novos, 0))}</b><span>documentos importados</span></div>
            <div className="metrica" style={{ paddingBottom: 12 }}><b>{fInt(importadas.reduce((a, r) => a + r.lancamentos, 0))}</b><span>lançamentos</span></div>
            <div className="metrica" style={{ paddingBottom: 12 }}><b>{fInt(resumo.mes.length)}</b><span>{resumo.mes.length === 1 ? 'dia com execução' : 'dias com execução'}</span></div>
          </div>
          <div style={{ flex: '0 1 360px', minWidth: 260, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="cal">
              {['D', 'S', 'T', 'Q', 'Q', 'S', 'S'].map((w, i) => <span key={i} className="mute" style={{ fontSize: 11, fontWeight: 700 }}>{w}</span>)}
              {celulas}
            </div>
            <div className="legenda">
              {legenda.map(k => <span key={k}><i style={{ background: cores(k).solid }} />{ST[k].label}</span>)}
              {proxima && <span><i style={{ border: '2px solid var(--st-neutral-solid)' }} />Agendado</span>}
            </div>
          </div>
        </div>
      </section>
    </div>
  )

  function UltimaExecucao() {
    const e = u!
    const andamento = e.status === 'andamento'
    const parou = e.etapas?.find(x => x.status === 'erro')
    const dur = duracao(e)
    return (
      <>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
            <span className="kicker">Última execução</span>
            <h2 style={{ fontSize: 22, margin: 0 }}>{cap(wd(e.data))}, {fDate(e.data)}{e.iniciado_em ? ` às ${fHoraCurta(e.iniciado_em)}` : ''}</h2>
            <span className="mute" style={{ fontSize: 13 }}>Período {periodoLabel(e)} · {e.lote ? 'lote ' + e.lote : 'nenhum lote gerado'} · empresa {e.sigla}</span>
          </div>
          <Status k={e.status} grande />
        </div>
        <div className="metricas">
          <div className="metrica"><b>{fInt(e.docs_novos)}</b><span>{andamento ? 'documentos novos a importar' : 'documentos novos importados'}</span></div>
          <div className="metrica"><b>{andamento ? '—' : fInt(e.lancamentos)}</b><span>lançamentos</span></div>
          <div className="metrica"><b>{andamento ? '—' : fInt(e.linhas)}</b><span>linhas na planilha</span></div>
          <div className="metrica"><b>{dur != null ? fDur(dur) : '—'}</b><span>{andamento ? 'decorridos até agora' : 'duração total'}</span></div>
        </div>
        {e.lote ? (
          <div className="totais-dc">
            <div><span className="kicker">Débito</span><b>{fBRL(e.debito)}</b></div>
            <span className="igual" aria-label="igual a">=</span>
            <div><span className="kicker">Crédito</span><b>{fBRL(e.credito)}</b></div>
            {e.debito === e.credito && <span className="ok-chip" style={{ marginLeft: 'auto' }}><Check size={16} />Débito e crédito conferem</span>}
          </div>
        ) : (
          <div className="caixa-info"><Info size={18} /><span>{andamento ? 'Débito e crédito aparecem quando a importação terminar.'
            : parou ? `Nenhum lote gerado — a execução parou na etapa ${parou.nome}. Os documentos do período entram na próxima execução.`
            : 'Nenhum lote gerado nesta execução.'}</span></div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span className="kicker">Etapas</span>
          <ol className="etapas">
            {(e.etapas || []).map(s => {
              const c = cores(s.status)
              return (
                <li key={s.n} style={{ ['--barra' as string]: c.solid } as CSSProperties}>
                  <span className="mute" style={{ fontSize: 12 }}>Etapa {s.n}</span>
                  <span className="nome"><span style={{ color: c.color, display: 'flex' }}><StatusIcone k={s.status} size={18} /></span>{s.nome}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: c.color }}>{ST[s.status].label}</span>
                  <span className="mute num" style={{ fontSize: 12 }}>{linhaEtapa(s)}</span>
                </li>
              )
            })}
          </ol>
        </div>
        <button className="btn btn-secondary" onClick={() => ir('detalhe', e.id)} style={{ alignSelf: 'flex-start', justifyContent: 'flex-start' }}>
          Ver detalhe da execução<ArrowRight size={16} />
        </button>
      </>
    )
  }
}

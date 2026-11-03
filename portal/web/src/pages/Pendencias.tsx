import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
import { Check, Info, Lock } from 'lucide-react'
import type { Contexto } from '../App'
import { api, fBRL, fDate, fInt, pl, type LinhaPlano, type Pendencias as Pend, type Segurado } from '../lib'
import { CampoAutocomplete, Carregando, useToast, type Opcao } from '../ui'

export default function Pendencias({ ctx }: { ctx: Contexto }) {
  const toast = useToast()
  const [p, setP] = useState<Pend | null>(null)
  const [plano, setPlano] = useState<LinhaPlano[]>([])
  const [entradas, setEntradas] = useState<Record<string, string>>({})
  const [erros, setErros] = useState<Record<string, string | null>>({})
  const [erro, setErro] = useState<string | null>(null)

  const carregar = useCallback(() => Promise.all([
    api<Pend>('/api/pendencias'), api<{ linhas: LinhaPlano[] }>('/api/tabelas/plano'),
  ]).then(([a, b]) => { setP(a); setPlano(b.linhas); setErro(null) }).catch(e => setErro(e.message)), [])
  useEffect(() => { carregar() }, [carregar])

  const contasErp = useMemo(() => {
    const m = new Map<string, Opcao>()
    plano.forEach(r => { if (!m.has(r.conta_erp)) m.set(r.conta_erp, { codigo: r.conta_erp, nome: r.nome_conta, sub: `Sintética ${r.sintetica_erp || '—'} · referencial ${r.conta_referencial || '—'}` }) })
    return [...m.values()].sort((a, b) => Number(a.codigo) - Number(b.codigo))
  }, [plano])

  if (erro) return <div className="erro-pagina">{erro}</div>
  if (!p) return <Carregando />

  const buscar = (pool: Opcao[], dica: string) => (q: string) => {
    const t = q.trim().toLowerCase()
    let l: Opcao[]
    if (t) l = pool.filter(a => a.codigo.startsWith(t) || a.nome.toLowerCase().includes(t))
    else {
      const palavras = dica.toLowerCase().split(/[^a-zà-ú]+/).filter(w => w.length > 4)
      l = pool.filter(a => palavras.some(w => a.nome.toLowerCase().includes(w)))
      if (!l.length) l = pool
    }
    return l.slice(0, 7)
  }
  const setEntrada = (k: string, v: string) => { setEntradas(e => ({ ...e, [k]: v })); setErros(e => ({ ...e, [k]: null })) }
  const entra = ctx.proxima ? `entra amanhã às ${ctx.resumo.config.horario}` : 'entra na próxima execução'

  const salvarConta = (sap: string, docs: number) => {
    const v = (entradas['conta:' + sap] || '').trim(); if (!v) return
    api<{ nova: boolean; linha: LinhaPlano }>('/api/pendencias/conta', { metodo: 'POST', corpo: { conta_sap: sap, conta_erp: v } })
      .then(r => { toast(`Salvo — ${entra}`, `${sap} → ${v}${r.nova ? ' (conta nova incluída no plano)' : ''} · ${pl(docs, 'documento liberado', 'documentos liberados')}`); carregar(); ctx.recarregar() })
      .catch(e => setErros(x => ({ ...x, ['conta:' + sap]: e.message })))
  }
  const desfazerConta = (sap: string) =>
    api(`/api/pendencias/conta/${sap}`, { metodo: 'DELETE' }).then(() => { carregar(); ctx.recarregar() }).catch(e => toast('Não foi possível desfazer', e.message, 'erro'))

  const contasPend = p.contas.filter(c => !c.salvo)
  const segPend = p.segurados.filter(s => !s.liberado)
  const salvoTexto = `Salvo — ${entra}`
  return (
    <div className="pilha">
      <div className="cab">
        <h1>Pendências</h1>
        <p>Preencha as correspondências que faltam entre SAP e ERP. Tudo que for salvo aqui entra na próxima execução{ctx.proxima ? ` (${ctx.proximaLabel})` : ''}.</p>
      </div>
      <div className="resumo-pend">
        <div style={{ ['--barra' as string]: contasPend.length ? 'var(--perigo)' : 'var(--st-ok-solid)' } as CSSProperties}>
          <b>{pl(contasPend.length, 'conta SAP sem conta ERP', 'contas SAP sem conta ERP')}</b>
          <span className="mute" style={{ fontSize: 13 }}>bloqueando {pl(segPend.filter(x => x.contas.length).length, 'documento', 'documentos')}</span>
        </div>
        <div style={{ ['--barra' as string]: segPend.length ? 'var(--st-warn-solid)' : 'var(--st-ok-solid)' } as CSSProperties}>
          <b>{pl(segPend.length, 'documento segurado', 'documentos segurados')}</b>
          <span className="mute" style={{ fontSize: 13 }}>somando {fBRL(segPend.reduce((a, x) => a + x.valor, 0))}</span>
        </div>
      </div>

      <section aria-label="Contas SAP sem conta ERP" className="superficie" style={{ gap: 14 }}>
        <div className="secao-cab">
          <div>
            <div className="secao-titulo"><h2>Contas SAP sem conta ERP</h2><span className="tag tag-perigo">Bloqueiam documentos</span></div>
            <p>Os documentos que usam estas contas ficam segurados. Informe a conta ERP correspondente — se ela ainda não existe no plano, use o próximo código livre.</p>
          </div>
          <span className="mute" style={{ fontSize: 13 }}>{pl(contasPend.length, 'pendente', 'pendentes')} de {fInt(p.contas.length)}</span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="table densa" style={{ minWidth: 1000 }}>
            <thead><tr><th>Conta SAP</th><th>Nome no SAP</th><th className="dir">Docs segurados</th><th className="dir">Linhas</th><th className="dir">Débito</th><th className="dir">Crédito</th><th>Exemplo de histórico</th><th style={{ width: 250 }}>Conta ERP</th><th style={{ width: 100 }} aria-label="Ação" /></tr></thead>
            <tbody>
              {p.contas.map(c => {
                const k = 'conta:' + c.codigo_sap
                return (
                  <tr key={k} className="topo-celula" style={{ background: c.salvo ? 'var(--st-ok-bg)' : undefined }}>
                    <td className="txt forte">{c.codigo_sap}</td>
                    <td className="txt">{c.nome_sap}</td>
                    <td className="txt dir">{fInt(c.docs)}</td>
                    <td className="txt dir">{fInt(c.linhas)}</td>
                    <td className="txt dir" style={{ whiteSpace: 'nowrap' }}>{fBRL(c.debito)}</td>
                    <td className="txt dir" style={{ whiteSpace: 'nowrap' }}>{fBRL(c.credito)}</td>
                    <td className="txt" style={{ maxWidth: 260, color: 'color-mix(in srgb, var(--color-text) 70%, transparent)' }}>“{c.historico_exemplo}”</td>
                    <td className="campo">
                      {c.salvo ? (
                        <div className="salvo"><b>{c.salvo.codigo} · {c.salvo.nome}</b><span>{salvoTexto}</span></div>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          <CampoAutocomplete valor={entradas[k] || ''} onValor={v => setEntrada(k, v)} opcoes={buscar(contasErp, c.nome_sap)}
                            titulo="Plano de contas ERP" placeholder="Código ou nome da conta" aria={`Conta ERP para ${c.codigo_sap}`} erro={erros[k]}
                            onEnter={() => salvarConta(c.codigo_sap, c.docs)} criar={{ label: `Criar conta ${p.codigo_livre} — próximo código livre`, codigo: String(p.codigo_livre) }} />
                          <div className="sugestao"><span className="mute">Próximo código livre:</span><button onClick={() => setEntrada(k, String(p.codigo_livre))}>{p.codigo_livre} · usar</button></div>
                          {erros[k] && <span className="erro-campo">{erros[k]}</span>}
                        </div>
                      )}
                    </td>
                    <td style={{ paddingTop: 10 }}>
                      {c.salvo ? <button className="btn btn-ghost" onClick={() => desfazerConta(c.codigo_sap)}>Desfazer</button>
                        : <button className="btn btn-primary" onClick={() => salvarConta(c.codigo_sap, c.docs)} disabled={!(entradas[k] || '').trim()} style={{ minHeight: 36 }}>Salvar</button>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {!p.contas.length && <div className="vazio">Nenhuma conta SAP sem conta ERP na última conversão.</div>}
        </div>
      </section>

      <section aria-label="Documentos segurados" className="superficie" style={{ gap: 14 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ fontSize: 16 }}>Documentos segurados</h2>
          <span className="mute" style={{ fontSize: 13 }}>{pl(segPend.length, 'segurado', 'segurados')} · {pl(p.segurados.length - segPend.length, 'liberado', 'liberados')}</span>
        </div>
        <div className="info-azul"><Info size={18} /><span>Ao salvar a conta, os documentos liberados entram na planilha da próxima execução do robô (importação na ERP à noite).</span></div>
        <div style={{ overflowX: 'auto' }}>
          <table className="table densa" style={{ minWidth: 820 }}>
            <thead><tr><th>Nº doc.</th><th>Data</th><th className="dir">Valor</th><th>Motivo</th><th>Segurado desde</th><th>Situação</th></tr></thead>
            <tbody>
              {p.segurados.map(s => (
                <tr key={s.doc}>
                  <td className="forte">{s.doc}</td>
                  <td>{fDate(s.data_lancamento)}</td>
                  <td className="dir" style={{ whiteSpace: 'nowrap' }}>{fBRL(s.valor)}</td>
                  <td>Falta conta ERP para {s.contas.map(c => `${c.conta}${c.nome ? ' – ' + c.nome : ''}`).join(', ')}</td>
                  <td>{fDate(s.desde)}</td>
                  <td><SituacaoSegurado s={s} entra={entra} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!p.segurados.length && <div className="vazio">Nenhum documento segurado.</div>}
        </div>
      </section>

    </div>
  )
}

const pill = (cor: string): CSSProperties => ({ display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 700, color: cor })

function SituacaoSegurado({ s, entra }: { s: Segurado; entra: string }) {
  if (s.liberado) return <span style={pill('var(--st-ok)')}><Check size={16} />Liberado · {entra}</span>
  return <span style={pill('var(--st-warn)')}><Lock size={16} />Segurado</span>
}

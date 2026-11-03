import { useCallback, useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { api, fInt, pl, type LinhaCC, type LinhaPlano } from '../lib'
import { Carregando, Dialogo, useToast } from '../ui'

const PS = 20
type Aba = 'plano' | 'cc'
type Dlg =
  | { tipo: 'form'; aba: Aba; modo: 'nova' | 'editar'; chaveAnterior?: string; form: Record<string, string>; erro?: string | null }
  | { tipo: 'excluir'; aba: Aba; chave: string; label: string }

const CAMPOS: Record<Aba, [string, string, string][]> = {
  plano: [['conta_sap', 'Conta SAP', ''], ['conta_erp', 'Conta ERP', ''], ['nome_conta', 'Nome', ''], ['sintetica_erp', 'Sintética ERP', ''], ['conta_referencial', 'Conta referencial', '']],
  cc: [['centro_custo_sap', 'CC SAP', ''], ['centro_custo_resumido', 'Resumido', ''], ['centro_custo_erp', 'CC ERP', '']],
}

export default function Tabelas() {
  const toast = useToast()
  const [aba, setAba] = useState<Aba>('plano')
  const [plano, setPlano] = useState<LinhaPlano[] | null>(null)
  const [ccs, setCcs] = useState<LinhaCC[] | null>(null)
  const [livre, setLivre] = useState(0)
  const [q, setQ] = useState('')
  const [pagina, setPagina] = useState(0)
  const [dlg, setDlg] = useState<Dlg | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  const carregar = useCallback(() => Promise.all([
    api<{ linhas: LinhaPlano[]; codigo_livre: number }>('/api/tabelas/plano'), api<{ linhas: LinhaCC[] }>('/api/tabelas/cc'),
  ]).then(([a, b]) => { setPlano(a.linhas); setLivre(a.codigo_livre); setCcs(b.linhas) }).catch(e => setErro(e.message)), [])
  useEffect(() => { carregar() }, [carregar])

  if (erro) return <div className="erro-pagina">{erro}</div>
  if (!plano || !ccs) return <Carregando />

  const ehPlano = aba === 'plano'
  const t = q.trim().toLowerCase()
  const fonte: (LinhaPlano | LinhaCC)[] = ehPlano ? plano : ccs
  const filtrada = !t ? fonte : ehPlano
    ? plano.filter(r => r.conta_sap.includes(t) || r.conta_erp.startsWith(t) || r.nome_conta.toLowerCase().includes(t))
    : ccs.filter(r => r.centro_custo_sap.includes(t) || r.centro_custo_erp.startsWith(t) || r.centro_custo_resumido.toLowerCase().includes(t))
  const paginas = Math.max(1, Math.ceil(filtrada.length / PS)); const pg = Math.min(pagina, paginas - 1)
  const unidade = ehPlano ? ['conta', 'contas'] : ['centro de custo', 'centros de custo']
  const encontrados = ehPlano ? ['conta encontrada', 'contas encontradas'] : ['centro de custo encontrado', 'centros de custo encontrados']

  const abrirForm = (modo: 'nova' | 'editar', r?: LinhaPlano | LinhaCC) => {
    const form: Record<string, string> = {}
    CAMPOS[aba].forEach(([k]) => { form[k] = r ? String((r as unknown as Record<string, string>)[k] || '') : '' })
    if (modo === 'nova' && ehPlano) form.conta_erp = String(livre)
    setDlg({ tipo: 'form', aba, modo, form, chaveAnterior: r ? (ehPlano ? (r as LinhaPlano).conta_sap : (r as LinhaCC).centro_custo_sap) : undefined })
  }
  const confirmar = () => {
    if (!dlg) return
    if (dlg.tipo === 'excluir') {
      api(`/api/tabelas/${dlg.aba}/${dlg.chave}`, { metodo: 'DELETE' })
        .then(() => { toast('Excluído', dlg.label, 'info'); setDlg(null); carregar() })
        .catch(e => toast('Não foi possível excluir', e.message, 'erro'))
      return
    }
    const f = dlg.form
    if (dlg.aba === 'plano') {
      if (!/^\d{10}$/.test(f.conta_sap || '')) return setDlg({ ...dlg, erro: 'A conta SAP tem 10 dígitos.' })
      if (!/^\d+$/.test(f.conta_erp || '')) return setDlg({ ...dlg, erro: 'Informe o código numérico da conta ERP.' })
      if (!(f.nome_conta || '').trim()) return setDlg({ ...dlg, erro: 'Informe o nome.' })
    } else {
      if (!/^\d+$/.test(f.centro_custo_sap || '')) return setDlg({ ...dlg, erro: 'Informe o CC SAP (só números).' })
      if (!(f.centro_custo_erp || '').trim()) return setDlg({ ...dlg, erro: 'Informe o CC ERP.' })
    }
    const corpo: Record<string, string | undefined> = { ...f, chave_anterior: dlg.modo === 'editar' ? dlg.chaveAnterior : undefined }
    if (dlg.aba === 'plano') corpo.nome_conta = f.nome_conta.trim().toUpperCase()
    api<{ linha: Record<string, string> }>(`/api/tabelas/${dlg.aba}`, { metodo: 'POST', corpo })
      .then(r => {
        const l = r.linha
        toast(dlg.aba === 'plano' ? (dlg.modo === 'nova' ? 'Conta incluída' : 'Conta atualizada') : (dlg.modo === 'nova' ? 'Centro de custo incluído' : 'Centro de custo atualizado'),
          dlg.aba === 'plano' ? `${l.conta_sap} → ${l.conta_erp} · ${l.nome_conta}` : `${l.centro_custo_sap} → ${l.centro_custo_erp}`)
        setDlg(null); carregar()
      })
      .catch(e => setDlg({ ...dlg, erro: e.message }))
  }

  return (
    <div className="pilha-20">
      <div className="cab">
        <h1>Tabelas de apoio</h1>
        <p>Correspondências SAP → ERP usadas pela conversão. Mudanças valem a partir da próxima execução.</p>
      </div>
      <div role="tablist" className="abas">
        {([['plano', 'Plano de contas (SAP → ERP)', pl(plano.length, 'conta', 'contas')], ['cc', 'Centros de custo (SAP → ERP)', pl(ccs.length, 'centro', 'centros')]] as const).map(([k, l, n]) => (
          <button key={k} role="tab" aria-selected={aba === k} onClick={() => { setAba(k); setPagina(0); setQ('') }}>{l}<span>{n}</span></button>
        ))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
        <div className="busca" style={{ flex: '0 1 380px', minWidth: 220 }}>
          <Search size={16} />
          <input className="input" type="search" value={q} onChange={e => { setQ(e.target.value); setPagina(0) }} aria-label="Buscar"
            placeholder={ehPlano ? 'Buscar por conta SAP, conta ERP ou nome' : 'Buscar por CC SAP, CC ERP ou nome'} />
        </div>
        <span className="mute" style={{ fontSize: 13 }}>{t ? pl(filtrada.length, encontrados[0], encontrados[1]) : pl(filtrada.length, unidade[0], unidade[1])}</span>
        <button className="btn btn-primary" onClick={() => abrirForm('nova')} style={{ marginLeft: 'auto' }}><Plus size={16} />{ehPlano ? 'Incluir conta' : 'Incluir centro de custo'}</button>
      </div>
      <div className="tabela-caixa">
        {ehPlano ? (
          <table className="table densa" style={{ minWidth: 860 }}>
            <thead><tr><th style={{ paddingLeft: 16 }}>Conta SAP</th><th>Conta ERP</th><th>Nome</th><th>Sintética ERP</th><th>Conta referencial</th><th style={{ width: 96 }} aria-label="Ações" /></tr></thead>
            <tbody>
              {(filtrada as LinhaPlano[]).slice(pg * PS, pg * PS + PS).map(r => (
                <tr key={r.conta_sap + r.conta_erp}>
                  <td style={{ paddingLeft: 16, fontWeight: 700 }}>{r.conta_sap}</td>
                  <td className="forte">{r.conta_erp}</td>
                  <td>{r.nome_conta}</td><td>{r.sintetica_erp}</td><td>{r.conta_referencial}</td>
                  <td style={{ paddingTop: 2, paddingBottom: 2 }}><Acoes rotulo={r.conta_sap} onEditar={() => abrirForm('editar', r)}
                    onExcluir={() => setDlg({ tipo: 'excluir', aba: 'plano', chave: r.conta_sap, label: `Conta ${r.conta_sap} → ${r.conta_erp} · ${r.nome_conta}` })} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="table densa" style={{ minWidth: 620 }}>
            <thead><tr><th style={{ paddingLeft: 16 }}>CC SAP</th><th>Resumido</th><th>CC ERP</th><th style={{ width: 96 }} aria-label="Ações" /></tr></thead>
            <tbody>
              {(filtrada as LinhaCC[]).slice(pg * PS, pg * PS + PS).map(r => (
                <tr key={r.centro_custo_sap}>
                  <td style={{ paddingLeft: 16, fontWeight: 700 }}>{r.centro_custo_sap}</td>
                  <td>{r.centro_custo_resumido}</td>
                  <td className="forte">{r.centro_custo_erp}</td>
                  <td style={{ paddingTop: 2, paddingBottom: 2 }}><Acoes rotulo={r.centro_custo_sap} onEditar={() => abrirForm('editar', r)}
                    onExcluir={() => setDlg({ tipo: 'excluir', aba: 'cc', chave: r.centro_custo_sap, label: `CC ${r.centro_custo_sap} → ${r.centro_custo_erp} · ${r.centro_custo_resumido}` })} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!filtrada.length && <div className="vazio">Nada encontrado para “{q}”.</div>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span className="mute" style={{ fontSize: 13 }}>
          {filtrada.length ? `Mostrando ${fInt(pg * PS + 1)}–${fInt(Math.min(filtrada.length, pg * PS + PS))} de ${pl(filtrada.length, unidade[0], unidade[1])} · página ${pg + 1} de ${paginas}` : 'Nenhum resultado'}
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary" onClick={() => setPagina(Math.max(0, pg - 1))} disabled={pg === 0}><ChevronLeft size={14} />Anterior</button>
          <button className="btn btn-secondary" onClick={() => setPagina(Math.min(paginas - 1, pg + 1))} disabled={pg >= paginas - 1}>Próxima<ChevronRight size={14} /></button>
        </div>
      </div>

      {dlg && dlg.tipo === 'excluir' && (
        <Dialogo titulo="Excluir correspondência?" okLabel="Excluir" onOk={confirmar} onCancelar={() => setDlg(null)}
          corpo={`${dlg.label}. Documentos que usarem essa ${dlg.aba === 'plano' ? 'conta' : 'CC'} SAP voltam a ${dlg.aba === 'plano' ? 'ficar segurados' : 'sair com CC 0'} até ser preenchida de novo.`} />
      )}
      {dlg && dlg.tipo === 'form' && (
        <Dialogo titulo={dlg.aba === 'plano' ? (dlg.modo === 'nova' ? 'Incluir conta' : 'Editar conta') : (dlg.modo === 'nova' ? 'Incluir centro de custo' : 'Editar centro de custo')}
          corpo={dlg.aba === 'plano' ? 'Correspondência usada pela conversão a partir da próxima execução.' : 'O CC ERP substitui o CC SAP na planilha de importação.'}
          okLabel="Salvar" erro={dlg.erro} onOk={confirmar} onCancelar={() => setDlg(null)}>
          <div style={{ display: 'grid', gap: 12 }}>
            {CAMPOS[dlg.aba].map(([k, label, ph]) => (
              <div className="field" key={k}>
                <label htmlFor={'f-' + k}>{label}</label>
                <input id={'f-' + k} className="input" value={dlg.form[k] || ''} placeholder={ph || (k === 'conta_erp' ? String(livre) : '')}
                  onChange={e => setDlg({ ...dlg, erro: null, form: { ...dlg.form, [k]: e.target.value } })} style={{ background: 'var(--color-surface)' }} />
              </div>
            ))}
          </div>
        </Dialogo>
      )}
    </div>
  )
}

function Acoes({ rotulo, onEditar, onExcluir }: { rotulo: string; onEditar: () => void; onExcluir: () => void }) {
  return (
    <div className="acoes-linha">
      <button className="btn btn-icon" aria-label={`Editar ${rotulo}`} title="Editar" onClick={onEditar}><Pencil size={15} /></button>
      <button className="btn btn-icon excluir" aria-label={`Excluir ${rotulo}`} title="Excluir" onClick={onExcluir}><Trash2 size={15} /></button>
    </div>
  )
}

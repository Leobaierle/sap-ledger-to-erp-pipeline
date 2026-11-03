import { useEffect, useState } from 'react'
import { api, fDate, pl, type Alterado } from '../lib'
import { Carregando } from '../ui'

export default function Alterados() {
  const [lista, setLista] = useState<Alterado[] | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [campo, setCampo] = useState<'all' | 'Texto' | 'Referência'>('all')
  useEffect(() => { api<{ alterados: Alterado[] }>('/api/alterados').then(d => setLista(d.alterados)).catch(e => setErro(e.message)) }, [])

  const filtrada = (lista || []).filter(a => campo === 'all' || a.campo === campo)
  return (
    <div className="pilha-20">
      <div className="cab">
        <h1>Alterados no SAP</h1>
        <p>Documentos que mudaram no SAP depois de importados. É só informativo: o robô não reimporta — se precisar, ajuste direto na ERP.</p>
      </div>
      <div className="filtros" style={{ gap: 12 }}>
        <span className="mute" style={{ fontSize: 13 }}>Campo alterado</span>
        <div role="group" aria-label="Campo alterado" className="seg">
          {([['all', 'Todos'], ['Texto', 'Texto'], ['Referência', 'Referência']] as const).map(([k, l]) =>
            <button key={k} aria-pressed={campo === k} onClick={() => setCampo(k)}>{l}</button>)}
        </div>
        <span className="mute" style={{ marginLeft: 'auto', fontSize: 13 }}>{pl(filtrada.length, 'documento alterado', 'documentos alterados')}</span>
      </div>
      {erro && <div className="erro-pagina">{erro}</div>}
      {!lista ? <Carregando /> : (
        <div className="tabela-caixa">
          <table className="table densa" style={{ minWidth: 980 }}>
            <thead><tr><th style={{ paddingLeft: 16 }}>Nº doc.</th><th>Data de lançamento</th><th>Lote importado</th><th>Campo alterado</th><th>Valor antes</th><th>Valor depois</th><th>Detectado em</th></tr></thead>
            <tbody>
              {filtrada.map((a, i) => (
                <tr key={i}>
                  <td className="forte" style={{ paddingLeft: 16 }}>{a.doc}</td>
                  <td>{fDate(a.data_lancamento)}</td>
                  <td>{a.lote}</td>
                  <td><span className="tag tag-neutral">{a.campo}</span></td>
                  <td className="mute" style={{ textDecoration: 'line-through' }}>{a.antes}</td>
                  <td style={{ fontWeight: 600 }}>{a.depois}</td>
                  <td>{fDate(a.detectado_em)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!filtrada.length && <div className="vazio">Nenhum documento alterado no SAP depois de importado.</div>}
        </div>
      )}
    </div>
  )
}

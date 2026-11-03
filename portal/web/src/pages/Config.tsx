import { Check, Info, RefreshCw, X } from 'lucide-react'
import type { Contexto } from '../App'
import { fDataHora } from '../lib'

// Os controles existem, mas ficam desabilitados até o robô e a orquestração (n8n) estarem em operação.
const DESAB = 'Disponível quando o robô estiver em operação.'

export default function Config({ ctx }: { ctx: Contexto }) {
  const sigla = ctx.resumo.config.ambiente
  const leitura = ctx.resumo.ultima?.etapas?.[0]
  const sapOk = leitura?.status === 'sucesso'
  return (
    <div className="pilha-20">
      <div className="cab">
        <h1>Configuração</h1>
        <p>Para onde o robô manda os lotes, quando ele roda e como está a conexão com o SAP.</p>
      </div>
      <div className="grade-config">
        <section aria-label="Destino na ERP" className="superficie" style={{ gap: 14 }}>
          <h2>Destino na ERP</h2>
          <dl className="dl-totais" style={{ gridTemplateColumns: 'auto minmax(0, 1fr)', gap: '0 16px' }}>
            <dt>Empresa</dt><dd style={{ textAlign: 'left', fontWeight: 400 }}>{sigla} · contabilidade da ACME</dd>
            <dt>Gravação</dt><dd style={{ textAlign: 'left', fontWeight: 400 }}>pela ERP API, um lote por noite</dd>
          </dl>
          <span className="nota-desab"><Info size={14} />A gravação na ERP só começa depois de autorizada pelo responsável.</span>
        </section>

        <section aria-label="Execução noturna" className="superficie" style={{ gap: 14 }}>
          <h2>Execução noturna</h2>
          <div className="field">
            <label htmlFor="icm-horario">Horário de início</label>
            <input id="icm-horario" className="input" type="time" value={ctx.resumo.config.horario || ''} disabled title={DESAB} style={{ width: 160, background: 'var(--color-bg)' }} readOnly />
          </div>
          <p className="mute" style={{ margin: 0, fontSize: 13, textWrap: 'pretty' }}>Todas as noites o robô busca o mês corrente do dia 1 até ontem e importa só os documentos novos.</p>
          <button className="btn btn-primary" disabled title={DESAB} style={{ alignSelf: 'flex-start' }}>Salvar horário</button>
          <span className="nota-desab"><Info size={14} />O horário ainda não foi definido; a execução será disparada pelo n8n.</span>
        </section>

        <section aria-label="Conexão com o SAP" className="superficie" style={{ gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <h2>Conexão com o SAP</h2>
            {leitura && (
              <span className="st" style={{ color: sapOk ? 'var(--st-ok)' : 'var(--st-err)', background: sapOk ? 'var(--st-ok-bg)' : 'var(--st-err-bg)' }}>
                {sapOk ? <Check size={16} /> : <X size={16} />}{sapOk ? 'Última leitura ok' : 'Última leitura falhou'}
              </span>
            )}
          </div>
          <dl className="dl-totais" style={{ gridTemplateColumns: 'auto minmax(0, 1fr)', gap: '0 16px' }}>
            <dt>Última leitura</dt><dd style={{ textAlign: 'left', fontWeight: 400 }}>{leitura?.terminado_em ? fDataHora(leitura.terminado_em) : 'Ainda não houve leitura'}</dd>
            <dt>Sistema</dt><dd style={{ textAlign: 'left', fontWeight: 400 }}>SAP ECC da ACME · produção · empresa 1200</dd>
            <dt>Acesso</dt><dd style={{ textAlign: 'left', fontWeight: 400 }}>RFC por SOAP (RFC_READ_TABLE), via VPN da ACME</dd>
            <dt>Usuário do robô</dt><dd style={{ textAlign: 'left', fontWeight: 400 }}>FISCAL2 (somente leitura)</dd>
          </dl>
          <button className="btn btn-secondary" disabled title={DESAB} style={{ alignSelf: 'flex-start' }}><RefreshCw size={16} />Testar conexão</button>
          <span className="nota-desab"><Info size={14} />{DESAB}</span>
        </section>
      </div>
    </div>
  )
}

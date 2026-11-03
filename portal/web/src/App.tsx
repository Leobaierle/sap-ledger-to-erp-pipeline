import { useCallback, useEffect, useState } from 'react'
import { ChevronRight, ClipboardList, Database, FileDiff, History, LayoutDashboard, LogOut, Moon, Settings, Sun, type LucideIcon } from 'lucide-react'
import { api, fDataHora, fDate, pl, proximaExecucao, type Resumo } from './lib'
import { Carregando } from './ui'
import { useUsuario } from './Acesso'
import Painel from './pages/Painel'
import Execucoes from './pages/Execucoes'
import Detalhe from './pages/Detalhe'
import Pendencias from './pages/Pendencias'
import Alterados from './pages/Alterados'
import Tabelas from './pages/Tabelas'
import Config from './pages/Config'

export type Rota = { pagina: string; id?: number }
const NAV: [string, string, LucideIcon][] = [
  ['painel', 'Painel', LayoutDashboard], ['execucoes', 'Execuções', History], ['pendencias', 'Pendências', ClipboardList],
  ['alterados', 'Alterados no SAP', FileDiff], ['tabelas', 'Tabelas de apoio', Database], ['config', 'Configuração', Settings],
]
const TITULOS: Record<string, string> = Object.fromEntries(NAV.map(([id, l]) => [id, l]))

function lerRota(): Rota {
  const [, pagina, id] = location.hash.replace(/^#/, '').split('/')
  if (pagina === 'execucoes' && id && /^\d+$/.test(id)) return { pagina: 'detalhe', id: Number(id) }
  return { pagina: TITULOS[pagina] ? pagina : 'painel' }
}
export const ir = (pagina: string, id?: number) => {
  location.hash = pagina === 'detalhe' ? `/execucoes/${id}` : `/${pagina}`
}

export interface Contexto { resumo: Resumo; recarregar: () => void; proxima: string | null; proximaLabel: string }

export default function App() {
  const [rota, setRota] = useState<Rota>(lerRota)
  const [tema, setTema] = useState<'light' | 'dark'>(() => { try { return localStorage.getItem('icm-tema') === 'dark' ? 'dark' : 'light' } catch { return 'light' } })
  const [largura, setLargura] = useState(window.innerWidth)
  const [resumo, setResumo] = useState<Resumo | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const usuario = useUsuario()

  const recarregar = useCallback(() => {
    api<Resumo>('/api/resumo').then(r => { setResumo(r); setErro(null) }).catch(e => setErro(e.message))
  }, [])
  useEffect(() => { recarregar() }, [recarregar])
  useEffect(() => {
    const h = () => { setRota(lerRota()); document.querySelector('main')?.scrollTo(0, 0); recarregar() }
    const w = () => setLargura(window.innerWidth)
    window.addEventListener('hashchange', h); window.addEventListener('resize', w)
    return () => { window.removeEventListener('hashchange', h); window.removeEventListener('resize', w) }
  }, [recarregar])
  useEffect(() => { try { localStorage.setItem('icm-tema', tema) } catch { /* sem storage */ } }, [tema])

  const sigla = resumo?.config.ambiente || 'EMP'
  const proxima = resumo ? proximaExecucao(resumo.config.horario) : null
  const proximaLabel = proxima ? `${fDate(proxima)} às ${resumo!.config.horario}` : 'a definir'
  const pendCount = resumo ? resumo.pendencias.contas : 0
  const ultima = resumo?.ultima
  const leituraSap = ultima?.etapas?.[0]
  const sapOk = leituraSap?.status === 'sucesso'

  const itensNav = NAV.map(([id, label, I]) => {
    const ativo = rota.pagina === id || (id === 'execucoes' && rota.pagina === 'detalhe')
    const badge = id === 'pendencias' ? pendCount : id === 'alterados' ? resumo?.alterados || 0 : 0
    return (
      <button key={id} className="nav-item" aria-current={ativo ? 'page' : undefined} onClick={() => ir(id)}>
        <span className="nav-ic"><I size={16} /></span>
        <span>{label}</span>
        {badge > 0 && (
          <span className="nav-badge" title={id === 'pendencias' ? pl(badge, 'pendência', 'pendências') : pl(badge, 'documento alterado', 'documentos alterados')}
            style={{ background: id === 'pendencias' ? 'var(--perigo-100)' : 'var(--color-neutral-100)', color: id === 'pendencias' ? 'var(--perigo-800)' : 'var(--color-muted)' }}>{badge}</span>
        )}
      </button>
    )
  })

  const ctx: Contexto | null = resumo ? { resumo, recarregar, proxima, proximaLabel } : null
  let pagina = <Carregando />
  if (erro && !resumo) pagina = <div className="erro-pagina">Não consegui falar com o servidor: {erro}</div>
  else if (ctx) {
    pagina = {
      painel: <Painel ctx={ctx} />, execucoes: <Execucoes ctx={ctx} />, detalhe: <Detalhe ctx={ctx} id={rota.id!} />,
      pendencias: <Pendencias ctx={ctx} />, alterados: <Alterados />, tabelas: <Tabelas />, config: <Config ctx={ctx} />,
    }[rota.pagina] || <Painel ctx={ctx} />
  }

  return (
    <div className="root" data-theme={tema}>
      <div className="corpo">
        <aside className="sidebar">
          <div className="marca">
            <img src="/logo.svg" alt="Logo" className="marca-logo" />
            <div className="marca-texto"><b>Importação Contábil</b><span>Robô diário · SAP → ERP</span></div>
          </div>
          <nav className="nav" aria-label="Principal"><div className="nav-titulo">ROBÔ NOTURNO</div>{itensNav}</nav>
          <div className="sidebar-rodape">
            <div className="linha"><span>Destino na ERP</span><span className="tag tag-accent">{sigla}</span></div>
            <div className="linha">
              <span className="ponto" style={{ background: leituraSap ? (sapOk ? 'var(--st-ok-solid)' : 'var(--st-err-solid)') : 'var(--st-none-solid)' }} />
              <span>{leituraSap ? (sapOk ? `SAP lido · ${fDataHora(leituraSap.terminado_em)}` : `Última leitura do SAP falhou · ${fDate(ultima!.data)}`) : 'SAP ainda não lido'}</span>
            </div>
            {usuario.sair && (
              <div className="usuario">
                <span title={usuario.email}>{usuario.email}</span>
                <button className="btn btn-secondary" onClick={usuario.sair}><LogOut size={14} />Sair</button>
              </div>
            )}
            <button className="btn btn-secondary" onClick={() => setTema(tema === 'dark' ? 'light' : 'dark')}>
              {tema === 'dark' ? <Sun size={14} /> : <Moon size={14} />}{tema === 'dark' ? 'Modo claro' : 'Modo escuro'}
            </button>
          </div>
        </aside>
        <main className="principal">
          <div className="pagina">
            <div className="pagina-meta">
              <nav className="trilha" aria-label="Trilha">
                {rota.pagina === 'detalhe'
                  ? <><button className="trilha-link" onClick={() => ir('execucoes')}>Execuções</button><ChevronRight size={14} /><span className="trilha-atual">Execução {rota.id}</span></>
                  : <span>Importação Contábil ACME</span>}
              </nav>
              {largura >= 700 && <span className="prox">Próxima execução: <strong>{proximaLabel}</strong></span>}
            </div>
            {pagina}
          </div>
        </main>
      </div>
    </div>
  )
}

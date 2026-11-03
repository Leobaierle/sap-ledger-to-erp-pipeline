// Login com a conta Microsoft corporativa, igual aos consoles (portal.example.com): quem faz o login é o
// console-gateway, que grava o cookie de sessão no domínio portal.example.com e volta para esta página.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { CircleAlert, Info, LoaderCircle } from 'lucide-react'
import { Carregando } from './ui'

type Me = { usuario: { email: string | null } | null; acesso: boolean; gateway: string; sem_login?: boolean }
type Usuario = { email: string; sair: (() => void) | null }

const UsuarioCtx = createContext<Usuario>({ email: '', sair: null })
export const useUsuario = () => useContext(UsuarioCtx)

// Códigos que o gateway devolve em ?login_error= (mesmos textos do pipeboard-app).
const ERROS: Record<string, string> = {
  ACCESS_PENDING: 'Pedido de acesso enviado. Assim que um administrador liberar, é só entrar de novo.',
  USER_INACTIVE: 'Sua conta está desativada. Fale com a TI.',
  IDENTITY_MISMATCH: 'Este e-mail já está ligado a outra conta Microsoft. Fale com a TI.',
  WRONG_DOMAIN: 'Entre com a sua conta Microsoft corporativa (@example.com).',
  NOT_MICROSOFT: 'Entre com a sua conta Microsoft corporativa (@example.com).',
  EXPIRED: 'O login expirou. Tente de novo.',
  MICROSOFT_ERROR: 'A Microsoft não concluiu o login. Tente de novo.',
  UNAVAILABLE: 'O login pela Microsoft está indisponível agora. Tente de novo em instantes.',
}

/** Lê e tira o ?login_error= da barra de endereço (fica antes do #). */
function tirarErroLogin(): string | null {
  const url = new URL(location.href)
  const codigo = url.searchParams.get('login_error')
  if (!codigo) return null
  url.searchParams.delete('login_error')
  history.replaceState(history.state, '', url.toString())
  return codigo
}

const MicrosoftMark = () => (
  <svg width={18} height={18} viewBox="0 0 21 21" aria-hidden="true">
    <rect x="1" y="1" width="9" height="9" fill="#f25022" /><rect x="11" y="1" width="9" height="9" fill="#7fba00" />
    <rect x="1" y="11" width="9" height="9" fill="#00a4ef" /><rect x="11" y="11" width="9" height="9" fill="#ffb900" />
  </svg>
)

export default function Acesso({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [falha, setFalha] = useState<string | null>(null)
  const [erroLogin] = useState(tirarErroLogin)
  const [saindo, setSaindo] = useState(false)

  const verificar = useCallback(() => {
    fetch('/api/me', { credentials: 'include' })
      .then(r => r.json().then((d: Me) => { setMe(d); setFalha(null) }))
      .catch(e => setFalha(e instanceof Error ? e.message : String(e)))
  }, [])
  useEffect(() => { verificar() }, [verificar])
  // a API responde 401 quando a sessão vence no meio do uso (lib.ts avisa por este evento)
  useEffect(() => {
    window.addEventListener('icm-sessao', verificar)
    return () => window.removeEventListener('icm-sessao', verificar)
  }, [verificar])

  const entrar = () => {
    setSaindo(true)
    const volta = new URL(location.href)
    volta.searchParams.delete('login_error')
    location.assign(`${me!.gateway}/auth/microsoft/start?return=${encodeURIComponent(volta.toString())}`)
  }
  const sair = useCallback(async () => {
    setSaindo(true)
    try { await fetch(`${me!.gateway}/auth/logout`, { method: 'POST', credentials: 'include' }) } catch { /* sai mesmo assim */ }
    setSaindo(false)
    verificar()
  }, [me, verificar])

  if (falha && !me) return <div className="tela-acesso"><div className="erro-pagina">Não consegui falar com o servidor: {falha}</div></div>
  if (!me) return <div className="tela-acesso"><Carregando /></div>

  if (me.usuario && me.acesso) {
    return <UsuarioCtx.Provider value={{ email: me.usuario.email || '', sair: me.sem_login ? null : sair }}>{children}</UsuarioCtx.Provider>
  }

  const pendente = erroLogin === 'ACCESS_PENDING'
  return (
    <div className="tela-acesso">
      <div className="cartao-acesso">
        {me.usuario ? (
          <>
            <img src="/logo.svg" alt="Logo" style={{ width: 48, height: 48, alignSelf: 'center' }} />
            <h1>Sem acesso</h1>
            <p>A conta <b>{me.usuario.email}</b> não tem acesso ao portal de Importação Contábil. Peça à TI a liberação da
              plataforma <b>Contabilidade</b> na lista de acessos do usuário.</p>
            <button className="btn btn-secondary" onClick={sair} disabled={saindo}>Trocar conta</button>
          </>
        ) : (
          <>
            <img src="/logo.svg" alt="Logo" style={{ height: 56, width: 56, alignSelf: 'center' }} />
            <h1>Importação Contábil</h1>
            <p>Entre para acompanhar o robô de importação da ACME.</p>
            {erroLogin && (
              <div className={pendente ? 'aviso-acesso' : 'aviso-acesso erro'}>
                {pendente ? <Info size={16} /> : <CircleAlert size={16} />}<span>{ERROS[erroLogin] || 'Não foi possível entrar. Tente de novo.'}</span>
              </div>
            )}
            <button className="btn btn-secondary btn-microsoft" onClick={entrar} disabled={saindo}>
              {saindo ? <LoaderCircle size={18} className="spin" /> : <MicrosoftMark />}Entrar com a conta Microsoft
            </button>
          </>
        )}
      </div>
    </div>
  )
}

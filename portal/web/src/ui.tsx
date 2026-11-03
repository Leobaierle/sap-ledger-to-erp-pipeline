import { createContext, useCallback, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import {
  CircleAlert, CircleCheck, CircleDashed, CircleHelp, CircleMinus, CircleX, Clock, Info, LoaderCircle, Plus, X,
  type LucideIcon,
} from 'lucide-react'
import { cores, ST, type StatusKey } from './lib'

const ICONE: Record<StatusKey, LucideIcon> = {
  agendado: Clock, andamento: LoaderCircle, sucesso: CircleCheck, pendencias: CircleAlert,
  erro: CircleX, verificar: CircleHelp, sem: CircleMinus, naoexec: CircleDashed,
}

export function StatusIcone({ k, size = 14 }: { k: StatusKey; size?: number }) {
  const I = ICONE[k]
  return <I size={size} className={k === 'andamento' ? 'spin' : undefined} aria-hidden style={{ flex: 'none' }} />
}

export function Status({ k, grande, label }: { k: StatusKey; grande?: boolean; label?: string }) {
  const c = cores(k)
  return (
    <span className={'st' + (grande ? ' st-lg' : '')} style={{ color: c.color, background: c.bg }}>
      <StatusIcone k={k} />{label || ST[k].label}
    </span>
  )
}

export function Carregando({ texto = 'Carregando…' }: { texto?: string }) {
  return <div className="carregando"><LoaderCircle size={16} className="spin" />{texto}</div>
}

// — avisos (toasts) —
type Toast = { id: number; titulo: string; desc: string; tipo: 'ok' | 'info' | 'erro' }
const ToastCtx = createContext<(titulo: string, desc: string, tipo?: Toast['tipo']) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [lista, setLista] = useState<Toast[]>([])
  const fechar = (id: number) => setLista(l => l.filter(t => t.id !== id))
  const mostrar = useCallback((titulo: string, desc: string, tipo: Toast['tipo'] = 'ok') => {
    const id = Date.now() + Math.random()
    setLista(l => [...l, { id, titulo, desc, tipo }].slice(-3))
    setTimeout(() => fechar(id), 5200)
  }, [])
  return (
    <ToastCtx.Provider value={mostrar}>
      {children}
      <div className="toasts" aria-live="polite">
        {lista.map(t => {
          const cor = t.tipo === 'info' ? 'var(--st-info)' : t.tipo === 'erro' ? 'var(--st-err)' : 'var(--st-ok)'
          const barra = t.tipo === 'info' ? 'var(--st-info-solid)' : t.tipo === 'erro' ? 'var(--st-err-solid)' : 'var(--st-ok-solid)'
          const I = t.tipo === 'info' ? Info : t.tipo === 'erro' ? CircleX : CircleCheck
          return (
            <div key={t.id} role="status" className="toast" style={{ ['--barra' as string]: barra } as CSSProperties}>
              <I size={18} style={{ color: cor }} />
              <b>{t.titulo}</b>
              <button onClick={() => fechar(t.id)} aria-label="Fechar aviso"><X size={16} /></button>
              <span>{t.desc}</span>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}

// — diálogo —
export function Dialogo({ titulo, corpo, children, erro, okLabel, onOk, onCancelar, ocupado }: {
  titulo: string; corpo: string; children?: ReactNode; erro?: string | null; okLabel: string
  onOk: () => void; onCancelar: () => void; ocupado?: boolean
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancelar() }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [onCancelar])
  return (
    <div className="dialog-backdrop" onClick={onCancelar} style={{ zIndex: 90, background: 'rgb(0 0 0 / 0.5)' }}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={titulo} onClick={e => e.stopPropagation()}
        style={{ width: 'min(480px, 100%)', background: 'var(--color-bg)' }}>
        <div className="dialog-title">{titulo}</div>
        <div className="dialog-body" style={{ textWrap: 'pretty' }}>{corpo}</div>
        {children}
        {erro && <span style={{ fontSize: 13, color: 'var(--perigo-700)' }}>{erro}</span>}
        <div className="dialog-actions">
          <button className="btn btn-secondary" onClick={onCancelar}>Cancelar</button>
          <button className="btn btn-primary" onClick={onOk} disabled={ocupado}>{okLabel}</button>
        </div>
      </div>
    </div>
  )
}

// — campo com autocomplete (conta ERP / CC ERP) —
export interface Opcao { codigo: string; nome: string; sub: string }

export function CampoAutocomplete({ valor, onValor, opcoes, titulo, placeholder, aria, erro, onEnter, criar }: {
  valor: string; onValor: (v: string) => void; opcoes: (q: string) => Opcao[]; titulo: string; placeholder: string
  aria: string; erro?: string | null; onEnter: () => void; criar?: { label: string; codigo: string }
}) {
  const ref = useRef<HTMLInputElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number; width: number } | null>(null)
  const [idx, setIdx] = useState(-1)
  const lista = pos ? opcoes(valor) : []
  const abrir = () => {
    const r = ref.current!.getBoundingClientRect(); const width = Math.max(r.width, 360)
    setPos({ left: Math.max(8, Math.min(r.left, window.innerWidth - width - 8)), top: r.bottom + 4, width }); setIdx(-1)
  }
  useEffect(() => {
    if (!pos) return
    const fechar = () => setPos(null)
    window.addEventListener('scroll', fechar, true); window.addEventListener('resize', fechar)
    return () => { window.removeEventListener('scroll', fechar, true); window.removeEventListener('resize', fechar) }
  }, [pos])
  const escolher = (c: string) => { onValor(c); setPos(null) }
  const tecla = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { setPos(null); return }
    if (!pos) { if (e.key === 'Enter') onEnter(); return }
    if (e.key === 'ArrowDown') { e.preventDefault(); setIdx(i => Math.min(lista.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx(i => Math.max(0, i - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (idx >= 0 && lista[idx]) escolher(lista[idx].codigo); else { setPos(null); onEnter() } }
  }
  return (
    <>
      <input ref={ref} className="input" value={valor} placeholder={placeholder} aria-label={aria} autoComplete="off"
        onChange={e => { onValor(e.target.value); if (!pos) abrir(); else setIdx(-1) }}
        onFocus={abrir} onBlur={() => setTimeout(() => setPos(null), 120)} onKeyDown={tecla}
        style={{ background: 'var(--color-bg)', borderColor: erro ? 'var(--perigo)' : undefined }} />
      {pos && (
        <div className="ac" role="listbox" style={{ left: pos.left, top: pos.top, width: pos.width }}>
          <span className="kicker">{titulo}</span>
          {lista.map((m, i) => (
            <button key={m.codigo} role="option" aria-selected={i === idx} className="ac-op" onMouseDown={e => { e.preventDefault(); escolher(m.codigo) }}>
              <b>{m.codigo}</b><span style={{ minWidth: 0 }}>{m.nome}<small>{m.sub}</small></span>
            </button>
          ))}
          {!lista.length && <span style={{ padding: '8px 12px', color: 'var(--mute)' }}>Nenhum resultado.</span>}
          {criar && (
            <button className="ac-criar" onMouseDown={e => { e.preventDefault(); escolher(criar.codigo) }}><Plus size={16} />{criar.label}</button>
          )}
        </div>
      )}
    </>
  )
}

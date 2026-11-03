import { useEffect, useState } from "react"

/** Roteamento por hash (#/, #/trabalho/<id>, #/plano, #/cc) — o site é uma página só servida pelo Flask. */
export function useRota(): string[] {
  const ler = () => window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean)
  const [partes, setPartes] = useState(ler)
  useEffect(() => {
    const aoMudar = () => setPartes(ler())
    window.addEventListener("hashchange", aoMudar)
    return () => window.removeEventListener("hashchange", aoMudar)
  }, [])
  return partes
}

export const ir = (caminho: string) => {
  window.location.hash = caminho
}

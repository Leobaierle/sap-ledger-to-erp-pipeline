import { BookOpenIcon, FileSpreadsheetIcon, NetworkIcon } from "lucide-react"

import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { useRota } from "@/lib/rota"
import Converter from "@/pages/Converter"
import TabelaApoio from "@/pages/TabelaApoio"

const NAVEGACAO = [
  { href: "#/", rotulo: "Converter", icone: FileSpreadsheetIcon, ativo: (r: string[]) => !r[0] || r[0] === "trabalho" },
  { href: "#/plano", rotulo: "Plano de contas", icone: BookOpenIcon, ativo: (r: string[]) => r[0] === "plano" },
  { href: "#/cc", rotulo: "Centros de custo", icone: NetworkIcon, ativo: (r: string[]) => r[0] === "cc" },
]

export default function App() {
  const rota = useRota()

  let pagina
  if (rota[0] === "plano") pagina = <TabelaApoio key="plano" nome="plano" />
  else if (rota[0] === "cc") pagina = <TabelaApoio key="cc" nome="cc" />
  else pagina = <Converter idTrabalho={rota[0] === "trabalho" ? rota[1] : undefined} />

  return (
    <TooltipProvider>
      <div className="min-h-svh">
        <header className="sticky top-0 z-40 border-b border-t-[3px] border-t-primary bg-card/90 backdrop-blur supports-backdrop-filter:bg-card/75">
          <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 sm:px-6">
            <a href="#/" className="flex items-center gap-3">
              <img src="/logo.svg" alt="" className="size-8" />
              <div className="font-heading text-base font-bold tracking-tight text-primary">
                Conversão <span className="text-foreground">ACME</span>
              </div>
            </a>
            <nav className="flex flex-wrap gap-1">
              {NAVEGACAO.map(({ href, rotulo, icone: Icone, ativo }) => {
                const on = ativo(rota)
                return (
                  <a
                    key={href}
                    href={href}
                    aria-current={on ? "page" : undefined}
                    className={
                      "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors " +
                      (on
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground")
                    }
                  >
                    <Icone className="size-4" />
                    {rotulo}
                  </a>
                )
              })}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">{pagina}</main>
      </div>
      <Toaster richColors position="top-right" />
    </TooltipProvider>
  )
}

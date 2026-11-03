import { useEffect, useMemo, useState } from "react"
import { Loader2Icon, OctagonXIcon, PencilIcon, PlusIcon, SearchIcon, Trash2Icon } from "lucide-react"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { buscarTabela, ErroApi, excluirLinha, inteiro, salvarLinha, type Tabela } from "@/lib/api"

const TEXTOS = {
  plano: {
    titulo: "Plano de contas",
    descricao: "Conta SAP → conta analítica da ERP.",
    novo: "Nova conta",
  },
  cc: {
    titulo: "Centros de custo",
    descricao: "Centro de custo SAP → ERP. Sem de-para, vai como 0.",
    novo: "Novo centro de custo",
  },
}

// Linhas renderizadas por vez: o plano tem ~770 linhas, a busca afunila.
const MAX_LINHAS = 300

export default function TabelaApoio({ nome }: { nome: "plano" | "cc" }) {
  const textos = TEXTOS[nome]
  const [tabela, setTabela] = useState<Tabela | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [busca, setBusca] = useState("")
  const [editando, setEditando] = useState<Record<string, string> | null>(null)
  const [ehNova, setEhNova] = useState(false)
  const [excluindo, setExcluindo] = useState<Record<string, string> | null>(null)

  const carregar = () =>
    buscarTabela(nome)
      .then(setTabela)
      .catch((e: ErroApi) => setErro(e.message))

  useEffect(() => {
    carregar()
  }, [nome]) // eslint-disable-line react-hooks/exhaustive-deps

  const filtradas = useMemo(() => {
    if (!tabela) return []
    const q = busca.trim().toLowerCase()
    if (!q) return tabela.linhas
    return tabela.linhas.filter((l) => tabela.campos.some((c) => (l[c] ?? "").toLowerCase().includes(q)))
  }, [tabela, busca])

  // chaves que aparecem mais de uma vez (ex.: conta SAP 2211999301 com duas contas ERP)
  const repetidas = useMemo(() => {
    const cont: Record<string, number> = {}
    for (const l of tabela?.linhas ?? []) cont[l[tabela!.chave]] = (cont[l[tabela!.chave]] ?? 0) + 1
    return new Set(Object.keys(cont).filter((k) => cont[k] > 1))
  }, [tabela])

  const abrirNova = () => {
    if (!tabela) return
    setEhNova(true)
    setEditando(Object.fromEntries(tabela.campos.map((c) => [c, ""])))
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-3xl space-y-1.5">
          <h1 className="text-xl font-semibold tracking-tight">{textos.titulo}</h1>
          <p className="text-sm text-muted-foreground">{textos.descricao}</p>
        </div>
        <Button onClick={abrirNova} disabled={!tabela}>
          <PlusIcon /> {textos.novo}
        </Button>
      </div>

      {erro && (
        <Alert variant="destructive">
          <OctagonXIcon />
          <AlertTitle>Não consegui carregar a tabela</AlertTitle>
          <AlertDescription>{erro}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative w-full max-w-sm">
              <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-8"
                placeholder="Buscar código ou nome"
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
              />
            </div>
            {tabela && (
              <span className="text-sm text-muted-foreground">
                {busca ? `${inteiro(filtradas.length)} de ${inteiro(tabela.linhas.length)}` : inteiro(tabela.linhas.length)}{" "}
                linha(s)
              </span>
            )}
          </div>

          {!tabela && !erro ? (
            <div className="space-y-2">
              {Array.from({ length: 8 }, (_, i) => (
                <Skeleton key={i} className="h-9" />
              ))}
            </div>
          ) : tabela ? (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    {tabela.rotulos.map((r) => (
                      <TableHead key={r}>{r}</TableHead>
                    ))}
                    <TableHead className="w-20" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtradas.slice(0, MAX_LINHAS).map((l, i) => (
                    <TableRow key={`${l[tabela.chave]}-${i}`} className="group">
                      {tabela.campos.map((c, j) => (
                        <TableCell key={c} className={j < 2 || c.endsWith("erp") ? "tabular-nums" : undefined}>
                          {j === 0 ? (
                            <span className="font-medium">
                              {l[c]}
                              {repetidas.has(l[c]) && (
                                <span className="ml-2 rounded bg-destructive/10 px-1.5 py-0.5 text-xs text-destructive">
                                  duplicada
                                </span>
                              )}
                            </span>
                          ) : (
                            l[c]
                          )}
                        </TableCell>
                      ))}
                      <TableCell>
                        <div className="flex justify-end gap-1 opacity-60 transition-opacity group-hover:opacity-100">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label="Editar"
                            onClick={() => {
                              setEhNova(false)
                              setEditando({ ...l })
                            }}
                          >
                            <PencilIcon />
                          </Button>
                          <Button variant="ghost" size="icon-sm" aria-label="Excluir" onClick={() => setExcluindo(l)}>
                            <Trash2Icon />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {filtradas.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={tabela.campos.length + 1} className="py-10 text-center text-muted-foreground">
                        Nada encontrado para "{busca}".
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
              {filtradas.length > MAX_LINHAS && (
                <p className="text-center text-sm text-muted-foreground">
                  Mostrando {MAX_LINHAS} de {inteiro(filtradas.length)} — use a busca para achar o resto.
                </p>
              )}
            </>
          ) : null}
        </CardContent>
      </Card>

      {tabela && editando && (
        <Editor
          nome={nome}
          tabela={tabela}
          linha={editando}
          nova={ehNova}
          aoFechar={() => setEditando(null)}
          aoSalvar={() => {
            setEditando(null)
            carregar()
          }}
        />
      )}

      <AlertDialog open={!!excluindo} onOpenChange={(o) => !o && setExcluindo(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir {excluindo && tabela ? excluindo[tabela.chave] : ""}?</AlertDialogTitle>
            <AlertDialogDescription>
              Se o código aparecer num próximo razão, volta como pendência.
              {excluindo && tabela && repetidas.has(excluindo[tabela.chave]) &&
                " Atenção: esse código tem mais de uma linha e todas serão excluídas."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={async () => {
                if (!excluindo || !tabela) return
                try {
                  await excluirLinha(nome, excluindo[tabela.chave])
                  toast.success(`${excluindo[tabela.chave]} excluído.`)
                  setExcluindo(null)
                  carregar()
                } catch (e) {
                  toast.error((e as ErroApi).message)
                }
              }}
            >
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function Editor({
  nome,
  tabela,
  linha,
  nova,
  aoFechar,
  aoSalvar,
}: {
  nome: string
  tabela: Tabela
  linha: Record<string, string>
  nova: boolean
  aoFechar: () => void
  aoSalvar: () => void
}) {
  const [valores, setValores] = useState(linha)
  const [salvando, setSalvando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault()
    setSalvando(true)
    setErro(null)
    try {
      await salvarLinha(nome, valores)
      toast.success(`${valores[tabela.chave]} salvo.`)
      aoSalvar()
    } catch (err) {
      setErro((err as ErroApi).message)
    } finally {
      setSalvando(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && aoFechar()}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={salvar} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{nova ? "Incluir" : `Editar ${linha[tabela.chave]}`}</DialogTitle>
            <DialogDescription>
              {nova ? "Se o código já existir, a linha antiga é substituída." : "Vale a partir da próxima conversão."}
            </DialogDescription>
          </DialogHeader>
          {erro && (
            <Alert variant="destructive">
              <OctagonXIcon />
              <AlertTitle>{erro}</AlertTitle>
            </Alert>
          )}
          <div className="grid gap-3">
            {tabela.campos.map((c, i) => (
              <div key={c} className="space-y-1.5">
                <Label htmlFor={c}>
                  {tabela.rotulos[i]}
                  {tabela.obrigatorios.includes(c) && <span className="text-destructive">*</span>}
                </Label>
                <Input
                  id={c}
                  value={valores[c] ?? ""}
                  disabled={!nova && c === tabela.chave}
                  onChange={(e) => setValores((v) => ({ ...v, [c]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={aoFechar}>
              Cancelar
            </Button>
            <Button type="submit" disabled={salvando}>
              {salvando && <Loader2Icon className="animate-spin" />} Salvar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

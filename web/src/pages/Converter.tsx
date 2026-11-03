import { useEffect, useRef, useState } from "react"
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  DownloadIcon,
  FileSpreadsheetIcon,
  FileUpIcon,
  Loader2Icon,
  OctagonXIcon,
  RotateCcwIcon,
  SaveIcon,
  Settings2Icon,
  XIcon,
} from "lucide-react"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  buscarTrabalho,
  converter,
  data,
  ErroApi,
  inteiro,
  reais,
  type Resultado,
  salvarPendencias,
  urlArquivo,
} from "@/lib/api"
import { ir } from "@/lib/rota"
import { cn } from "@/lib/utils"

// ================================================================ página

export default function Converter({ idTrabalho }: { idTrabalho?: string }) {
  const [resultado, setResultado] = useState<Resultado | null>(null)
  const [carregando, setCarregando] = useState(false)
  const [erroCarga, setErroCarga] = useState<string | null>(null)

  // abre um trabalho pelo link (#/trabalho/<id>), ex.: depois de recarregar a página
  useEffect(() => {
    if (!idTrabalho) {
      setResultado(null)
      return
    }
    if (resultado?.id === idTrabalho) return
    setCarregando(true)
    setErroCarga(null)
    buscarTrabalho(idTrabalho)
      .then(setResultado)
      .catch((e: ErroApi) => setErroCarga(e.message))
      .finally(() => setCarregando(false))
  }, [idTrabalho]) // eslint-disable-line react-hooks/exhaustive-deps

  const aoConverter = (r: Resultado) => {
    setResultado(r)
    ir(`/trabalho/${r.id}`)
  }

  if (idTrabalho && carregando) return <CarregandoResultado />
  if (idTrabalho && erroCarga)
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <Alert variant="destructive">
          <OctagonXIcon />
          <AlertTitle>Não encontrei essa conversão</AlertTitle>
          <AlertDescription>{erroCarga}</AlertDescription>
        </Alert>
        <Button variant="outline" onClick={() => ir("/")}>
          <RotateCcwIcon /> Converter um arquivo
        </Button>
      </div>
    )
  if (idTrabalho && resultado) return <VerResultado resultado={resultado} aoAtualizar={setResultado} />
  return <Envio aoConverter={aoConverter} />
}

// ================================================================ envio

function Envio({ aoConverter }: { aoConverter: (r: Resultado) => void }) {
  const [modo, setModo] = useState<"primeira" | "complementar">("primeira")
  const [arquivo, setArquivo] = useState<File | null>(null)
  const [anteriores, setAnteriores] = useState<File[]>([])
  const [limite, setLimite] = useState("")
  const [lote, setLote] = useState("")
  const [etapa, setEtapa] = useState<"parado" | "enviando" | "processando">("parado")
  const [pctEnvio, setPctEnvio] = useState(0)
  const [segundos, setSegundos] = useState(0)
  const [erro, setErro] = useState<ErroApi | null>(null)

  useEffect(() => {
    if (etapa !== "processando") return
    setSegundos(0)
    const t = setInterval(() => setSegundos((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [etapa])

  const complementar = modo === "complementar"
  const ocupado = etapa !== "parado"
  const pronto = !!arquivo && (!complementar || anteriores.length > 0)

  const enviar = async () => {
    if (!arquivo || !pronto) return
    setErro(null)
    setEtapa("enviando")
    setPctEnvio(0)
    try {
      const r = await converter(arquivo, { limite, lote, anteriores: complementar ? anteriores : [] }, (pct) => {
        setPctEnvio(pct)
        if (pct >= 100) setEtapa("processando")
      })
      if (r.erros.length) toast.error("Conversão concluída com erros — o arquivo não foi gerado.")
      else if (r.pronto) toast.success("Arquivo pronto.")
      else toast.warning("Há pendências para preencher.")
      aoConverter(r)
    } catch (e) {
      setErro(e as ErroApi)
      setEtapa("parado")
    }
  }

  return (
    <div className="max-w-2xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-heading text-2xl font-bold tracking-tight">Converter razão</h1>
        <div className="inline-flex rounded-full bg-card p-1 shadow-sm ring-1 ring-foreground/8" role="group" aria-label="Tipo de importação">
          {(
            [
              ["primeira", "Primeira importação"],
              ["complementar", "Complementar"],
            ] as const
          ).map(([v, texto]) => (
            <button
              key={v}
              type="button"
              disabled={ocupado}
              aria-pressed={modo === v}
              onClick={() => setModo(v)}
              className={cn(
                "rounded-full px-4 py-1.5 text-sm font-medium transition-colors disabled:opacity-60",
                modo === v ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {texto}
            </button>
          ))}
        </div>
      </div>

      {erro && (
        <Alert variant="destructive">
          <OctagonXIcon />
          <AlertTitle>{erro.message}</AlertTitle>
          {erro.detalhes.length > 0 && (
            <AlertDescription>
              <ul className="list-disc pl-4">
                {erro.detalhes.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </AlertDescription>
          )}
        </Alert>
      )}

      <Card>
        <CardContent className="space-y-5">
          {complementar ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Zona
                titulo="Razão SAP já importado"
                dica="Mais de um? Envie na ordem."
                multiplo
                arquivos={anteriores}
                desabilitado={ocupado}
                aoEscolher={(fs) => {
                  setAnteriores((a) => [...a, ...fs])
                  setErro(null)
                }}
                aoTirar={(i) => setAnteriores((l) => l.filter((_, j) => j !== i))}
              />
              <Zona
                titulo="Razão novo"
                dica="O mês inteiro, extraído de novo."
                arquivos={arquivo ? [arquivo] : []}
                desabilitado={ocupado}
                aoEscolher={(fs) => {
                  setArquivo(fs[0])
                  setErro(null)
                }}
                aoTirar={() => setArquivo(null)}
              />
            </div>
          ) : (
            <Zona
              arquivos={arquivo ? [arquivo] : []}
              desabilitado={ocupado}
              aoEscolher={(fs) => {
                setArquivo(fs[0])
                setErro(null)
              }}
              aoTirar={() => setArquivo(null)}
            />
          )}

          {ocupado && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Loader2Icon className="size-4 animate-spin text-primary" />
                {etapa === "enviando" ? `Enviando… ${pctEnvio}%` : `Convertendo… ${segundos} s`}
              </div>
              <Progress value={etapa === "enviando" ? pctEnvio : null} />
            </div>
          )}

          <Collapsible>
            <div className="flex flex-wrap items-center gap-3">
              <Button size="lg" disabled={!pronto || ocupado} onClick={enviar}>
                {ocupado ? <Loader2Icon className="animate-spin" /> : <FileSpreadsheetIcon />}
                {ocupado ? "Convertendo…" : complementar ? "Gerar complementar" : "Converter"}
              </Button>
              <CollapsibleTrigger
                render={
                  <Button variant="ghost" size="sm" className="group text-muted-foreground" disabled={ocupado} />
                }
              >
                <Settings2Icon /> Opções
                <ChevronDownIcon className="transition-transform group-data-panel-open:rotate-180" />
              </CollapsibleTrigger>
            </div>
            <CollapsibleContent>
              <div className="grid gap-4 pt-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="limite">Linhas por parte</Label>
                  <Input
                    id="limite"
                    inputMode="numeric"
                    placeholder="49998"
                    value={limite}
                    onChange={(e) => setLimite(e.target.value.replace(/\D/g, ""))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="lote">Lote da 1ª parte</Label>
                  <Input
                    id="lote"
                    inputMode="numeric"
                    placeholder="automático"
                    value={lote}
                    onChange={(e) => setLote(e.target.value.replace(/\D/g, ""))}
                  />
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>
        </CardContent>
      </Card>
    </div>
  )
}

function Zona({
  titulo,
  dica,
  multiplo,
  arquivos,
  desabilitado,
  aoEscolher,
  aoTirar,
}: {
  titulo?: string
  dica?: string
  multiplo?: boolean
  arquivos: File[]
  desabilitado: boolean
  aoEscolher: (f: File[]) => void
  aoTirar: (i: number) => void
}) {
  const [arrastando, setArrastando] = useState(false)
  const entrada = useRef<HTMLInputElement>(null)
  const pegar = (l: FileList | null) => {
    const fs = Array.from(l ?? [])
    if (fs.length) aoEscolher(multiplo ? fs : fs.slice(0, 1))
  }
  return (
    <div className="space-y-2">
      {titulo && <div className="text-sm font-medium">{titulo}</div>}
      <button
        type="button"
        disabled={desabilitado}
        onClick={() => entrada.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setArrastando(true)
        }}
        onDragLeave={() => setArrastando(false)}
        onDrop={(e) => {
          e.preventDefault()
          setArrastando(false)
          if (!desabilitado) pegar(e.dataTransfer.files)
        }}
        className={cn(
          "group flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-all outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
          arrastando
            ? "scale-[1.01] border-primary bg-secondary"
            : "border-brand-soft bg-secondary/40 hover:border-primary hover:bg-secondary/70",
          desabilitado && "pointer-events-none opacity-60",
        )}
      >
        <span className="flex size-11 items-center justify-center rounded-full bg-card text-primary shadow-sm ring-1 ring-primary/15 transition-transform group-hover:-translate-y-0.5">
          <FileUpIcon className="size-5" />
        </span>
        <span className="text-sm font-semibold">
          {arquivos.length && !multiplo ? "Trocar arquivo" : "Escolher ou arrastar"}
        </span>
        <span className="text-xs text-muted-foreground">{dica ?? ".xlsx ou .xls do SAP"}</span>
      </button>
      <input
        ref={entrada}
        type="file"
        multiple={multiplo}
        accept=".xlsx,.xlsm,.xls,.txt"
        className="hidden"
        onChange={(e) => {
          pegar(e.target.files)
          e.target.value = ""
        }}
      />
      {arquivos.map((a, i) => (
        <div key={`${a.name}-${i}`} className="flex items-center gap-2 rounded-md border bg-muted/40 py-1.5 pr-1.5 pl-3">
          <FileSpreadsheetIcon className="size-4 shrink-0 text-primary" />
          <span className="min-w-0 flex-1 truncate text-sm" title={a.name}>
            {a.name}
          </span>
          <span className="shrink-0 text-xs text-muted-foreground">{(a.size / 1024 / 1024).toFixed(1)} MB</span>
          {!desabilitado && (
            <Button variant="ghost" size="icon-sm" aria-label="Tirar arquivo" onClick={() => aoTirar(i)}>
              <XIcon />
            </Button>
          )}
        </div>
      ))}
    </div>
  )
}

function CarregandoResultado() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-80" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      <Skeleton className="h-64" />
    </div>
  )
}

// ================================================================ resultado

function VerResultado({ resultado: r, aoAtualizar }: { resultado: Resultado; aoAtualizar: (r: Resultado) => void }) {
  const temPendencias =
    r.pendencias.contas.length + r.pendencias.duplicadas.length + r.pendencias.centros_custo.length > 0
  const compl = r.complementar
  const fora = [
    r.totais.linhas_zeradas > 0 && `${inteiro(r.totais.linhas_zeradas)} com valor zero`,
    compl && compl.linhas_ja_lancadas > 0 && `${inteiro(compl.linhas_ja_lancadas)} de documentos já lançados`,
  ].filter(Boolean)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-heading text-2xl font-bold tracking-tight">
              {r.modo === "complementar" ? "Complementar" : "Resultado"}
            </h1>
            {r.erros.length > 0 ? (
              <Badge variant="destructive">com erros</Badge>
            ) : r.pronto ? (
              <Badge className="bg-success-soft text-success">pronto</Badge>
            ) : (
              <Badge className="bg-warning-soft text-warning">pendências</Badge>
            )}
          </div>
          <p className="truncate text-sm text-muted-foreground">
            {r.arquivo} · {data(r.periodo[0])} a {data(r.periodo[1])}
          </p>
        </div>
        <Button variant="outline" onClick={() => ir("/")}>
          <RotateCcwIcon /> Novo
        </Button>
      </div>

      <Status r={r} />

      <div className="space-y-2">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Numero rotulo={compl ? "Linhas novas" : "Linhas para importar"} valor={inteiro(r.totais.linhas_importar)} destaque />
          <Numero rotulo={compl ? "Documentos novos" : "Lançamentos"} valor={inteiro(r.totais.lancamentos)} />
          <Numero rotulo="Débitos (R$)" valor={reais(r.totais.debito)} />
          <Numero rotulo="Créditos (R$)" valor={reais(r.totais.credito)} />
        </div>
        <p className="text-xs text-muted-foreground">
          O razão tem {inteiro(r.totais.linhas_sap)} linhas{fora.length > 0 && `; ficaram de fora ${fora.join(" e ")}`}.
        </p>
      </div>

      {temPendencias && !r.pronto && <Pendencias r={r} aoAtualizar={aoAtualizar} />}

      {r.avisos.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangleIcon className="size-4 text-warning" /> Para conferir
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {r.avisos.map((a) => (
                <li key={a} className="flex gap-2">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-warning" />
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {r.pronto && r.partes.length > 0 && <Partes r={r} />}

      {/* com o arquivo pronto, o que sobra é opcional (centros de custo) e vai para o fim */}
      {temPendencias && r.pronto && <Pendencias r={r} aoAtualizar={aoAtualizar} />}
    </div>
  )
}

function Status({ r }: { r: Resultado }) {
  if (r.erros.length > 0)
    return (
      <Alert variant="destructive">
        <OctagonXIcon />
        <AlertTitle>Não gerei o arquivo</AlertTitle>
        <AlertDescription>
          <ul className="list-disc pl-4">
            {r.erros.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </AlertDescription>
      </Alert>
    )
  if (!r.pronto)
    return (
      <Alert className="border-warning/30 bg-warning-soft">
        <AlertTriangleIcon className="text-warning" />
        <AlertTitle>Preencha as pendências abaixo e salve</AlertTitle>
      </Alert>
    )
  return (
    <Card className="bg-gradient-to-r from-success-soft to-card ring-success/25">
      <CardContent className="flex flex-wrap items-center gap-4">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-success text-white shadow-sm">
          <CheckCircle2Icon className="size-6" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-heading text-base font-semibold">Pronto para importar na ERP</div>
          <div className="text-sm text-muted-foreground">
            {r.partes.length === 1 ? "1 aba" : `${r.partes.length} abas`} na planilha
          </div>
        </div>
        <Button size="lg" nativeButton={false} render={<a href={urlArquivo(r.id)} download />}>
          <DownloadIcon /> Baixar planilha
        </Button>
      </CardContent>
    </Card>
  )
}

function Numero({ rotulo, valor, destaque }: { rotulo: string; valor: string; destaque?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-xl px-4 py-3 shadow-sm ring-1",
        destaque
          ? "bg-gradient-to-br from-primary to-[oklch(0.42_0.06_194)] text-primary-foreground ring-primary/30"
          : "bg-card ring-foreground/8",
      )}
    >
      <div className={cn("text-xs", destaque ? "text-primary-foreground/80" : "text-muted-foreground")}>{rotulo}</div>
      <div className="mt-0.5 font-heading text-xl font-bold tabular-nums">{valor}</div>
    </div>
  )
}

function Partes({ r }: { r: Resultado }) {
  const nome = (n: number) =>
    r.modo === "complementar" ? (r.partes.length === 1 ? "COMPLEMENTAR" : `${n}° COMPLEMENTAR`) : `${n}° IMPORTAÇÃO`
  return (
    <Card>
      <CardHeader>
        <CardTitle>Abas da planilha</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Aba</TableHead>
              <TableHead className="text-right">Lote</TableHead>
              <TableHead className="text-right">Linhas</TableHead>
              <TableHead className="text-right">Lançamentos</TableHead>
              <TableHead className="text-right">Débitos (R$)</TableHead>
              <TableHead className="text-right">Créditos (R$)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody className="tabular-nums">
            {r.partes.map((p) => (
              <TableRow key={p.numero}>
                <TableCell className="font-medium">{nome(p.numero)}</TableCell>
                <TableCell className="text-right">{p.lote}</TableCell>
                <TableCell className="text-right">{inteiro(p.linhas)}</TableCell>
                <TableCell className="text-right">
                  {inteiro(p.lancamento_de)} a {inteiro(p.lancamento_ate)}
                </TableCell>
                <TableCell className="text-right">{reais(p.debito)}</TableCell>
                <TableCell className="text-right">{reais(p.credito)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
          {r.partes.length > 1 && (
            <TableFooter className="tabular-nums">
              <TableRow>
                <TableCell>Total</TableCell>
                <TableCell />
                <TableCell className="text-right">{inteiro(r.totais.linhas_importar)}</TableCell>
                <TableCell className="text-right">{inteiro(r.totais.lancamentos)}</TableCell>
                <TableCell className="text-right">{reais(r.totais.debito)}</TableCell>
                <TableCell className="text-right">{reais(r.totais.credito)}</TableCell>
              </TableRow>
            </TableFooter>
          )}
        </Table>
      </CardContent>
    </Card>
  )
}

// ================================================================ pendências

function Pendencias({ r, aoAtualizar }: { r: Resultado; aoAtualizar: (r: Resultado) => void }) {
  const { contas, duplicadas, centros_custo } = r.pendencias
  const [valContas, setValContas] = useState<Record<string, { conta_erp: string; nome_conta: string }>>({})
  const [valDup, setValDup] = useState<Record<string, string>>({})
  const [valCC, setValCC] = useState<Record<string, string>>({})
  const [salvando, setSalvando] = useState(false)
  const [erros, setErros] = useState<string[]>([])

  // novo resultado (depois de salvar) → começa os campos do zero
  useEffect(() => {
    setValContas(Object.fromEntries(contas.map((c) => [c.conta, { conta_erp: "", nome_conta: c.nome_sap }])))
    setValDup({})
    setValCC({})
  }, [r]) // eslint-disable-line react-hooks/exhaustive-deps

  const preenchidos =
    Object.values(valContas).filter((v) => v.conta_erp.trim()).length +
    Object.values(valDup).filter(Boolean).length +
    Object.values(valCC).filter((v) => v.trim()).length

  const salvar = async () => {
    setSalvando(true)
    setErros([])
    try {
      const novo = await salvarPendencias(r.id, { contas: valContas, duplicadas: valDup, centros_custo: valCC })
      aoAtualizar(novo)
      for (const s of novo.salvos ?? []) {
        if (s.startsWith("atenção")) toast.warning(s)
      }
      toast.success(
        novo.pronto ? "Salvo — o arquivo está pronto para baixar." : "Salvo nas tabelas. Ainda há pendências.",
      )
    } catch (e) {
      const err = e as ErroApi
      setErros(err.detalhes.length ? err.detalhes : [err.message])
    } finally {
      setSalvando(false)
    }
  }

  return (
    <Card className={r.pronto ? undefined : "ring-1 ring-warning/20"}>
      <CardHeader>
        <CardTitle>{r.pronto ? "Completar o de-para (opcional)" : "Pendências"}</CardTitle>
        <CardDescription>
          Fica salvo no <a className="underline" href="#/plano">plano de contas</a> e nos{" "}
          <a className="underline" href="#/cc">centros de custo</a>, e vale para os próximos meses.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-8">
        {erros.length > 0 && (
          <Alert variant="destructive">
            <OctagonXIcon />
            <AlertTitle>Não salvei — corrija:</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-4">
                {erros.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        {contas.length > 0 && (
          <section className="space-y-3">
            <TituloSecao
              titulo="Contas SAP sem conta ERP"
              badge={<Badge variant="destructive">bloqueia o download</Badge>}
              texto={
                <>
                  Informe o código analítico da ERP.
                  {r.maior_conta_erp && (
                    <>
                      {" "}
                      Maior cadastrado: <b>{r.maior_conta_erp}</b>.
                    </>
                  )}
                </>
              }
            />
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Conta SAP</TableHead>
                  <TableHead className="text-right">Linhas</TableHead>
                  <TableHead className="text-right">Débitos (R$)</TableHead>
                  <TableHead className="text-right">Créditos (R$)</TableHead>
                  <TableHead>Exemplo de histórico</TableHead>
                  <TableHead className="w-28">Conta ERP *</TableHead>
                  <TableHead className="min-w-56">Nome da conta</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {contas.map((c, i) => (
                  <TableRow key={c.conta}>
                    <TableCell>
                      <div className="font-medium tabular-nums">{c.conta}</div>
                      <div className="text-xs text-muted-foreground">{c.nome_sap || "sem nome no BASEPLANO"}</div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{inteiro(c.linhas)}</TableCell>
                    <TableCell className="text-right tabular-nums">{reais(c.debito)}</TableCell>
                    <TableCell className="text-right tabular-nums">{reais(c.credito)}</TableCell>
                    <TableCell className="max-w-64 truncate text-muted-foreground" title={c.exemplo}>
                      {c.exemplo}
                    </TableCell>
                    <TableCell>
                      <Input
                        inputMode="numeric"
                        aria-label={`Conta ERP para ${c.conta}`}
                        placeholder={r.maior_conta_erp ? String(r.maior_conta_erp + i + 1) : ""}
                        value={valContas[c.conta]?.conta_erp ?? ""}
                        onChange={(e) =>
                          setValContas((v) => ({
                            ...v,
                            [c.conta]: { ...v[c.conta], conta_erp: e.target.value.replace(/\D/g, "") },
                          }))
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        aria-label={`Nome da conta ${c.conta}`}
                        value={valContas[c.conta]?.nome_conta ?? ""}
                        onChange={(e) =>
                          setValContas((v) => ({ ...v, [c.conta]: { ...v[c.conta], nome_conta: e.target.value } }))
                        }
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </section>
        )}

        {duplicadas.length > 0 && (
          <section className="space-y-3">
            <TituloSecao
              titulo="Contas SAP com mais de uma conta ERP no plano"
              badge={<Badge variant="destructive">bloqueia o download</Badge>}
              texto="Escolha a conta certa; a outra sai do plano."
            />
            <div className="divide-y rounded-lg border">
              {duplicadas.map((d) => (
                <div key={d.conta} className="flex flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3">
                  <span className="w-32 font-medium tabular-nums">{d.conta}</span>
                  <RadioGroup
                    className="flex flex-wrap gap-6"
                    value={valDup[d.conta] ?? ""}
                    onValueChange={(v) => setValDup((s) => ({ ...s, [d.conta]: String(v) }))}
                  >
                    {d.opcoes.map((o) => (
                      <Label key={o} className="flex items-center gap-2 font-normal">
                        <RadioGroupItem value={o} /> ERP {o}
                      </Label>
                    ))}
                  </RadioGroup>
                </div>
              ))}
            </div>
          </section>
        )}

        {centros_custo.length > 0 && (
          <section className="space-y-3">
            <TituloSecao
              titulo="Centros de custo sem de-para"
              badge={<Badge className="bg-warning-soft text-warning">se ficar em branco, sai como 0</Badge>}
              texto="Não impedem o download."
            />
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Centro de custo SAP</TableHead>
                  <TableHead className="text-right">Linhas</TableHead>
                  <TableHead className="text-right">Valor (R$)</TableHead>
                  <TableHead>Conta SAP (exemplo)</TableHead>
                  <TableHead>Exemplo de histórico</TableHead>
                  <TableHead className="w-28">CC ERP</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {centros_custo.map((c) => (
                  <TableRow key={c.cc}>
                    <TableCell className="font-medium tabular-nums">{c.cc}</TableCell>
                    <TableCell className="text-right tabular-nums">{inteiro(c.linhas)}</TableCell>
                    <TableCell className="text-right tabular-nums">{reais(c.valor)}</TableCell>
                    <TableCell className="tabular-nums">{c.conta}</TableCell>
                    <TableCell className="max-w-64 truncate text-muted-foreground" title={c.exemplo}>
                      {c.exemplo}
                    </TableCell>
                    <TableCell>
                      <Input
                        inputMode="numeric"
                        aria-label={`CC ERP para ${c.cc}`}
                        value={valCC[c.cc] ?? ""}
                        onChange={(e) => setValCC((v) => ({ ...v, [c.cc]: e.target.value.replace(/\D/g, "") }))}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </section>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t pt-5">
          <Button size="lg" disabled={salvando || preenchidos === 0} onClick={salvar}>
            {salvando ? <Loader2Icon className="animate-spin" /> : <SaveIcon />}
            {salvando ? "Salvando e convertendo…" : "Salvar e converter de novo"}
          </Button>
          <span className="text-sm text-muted-foreground">
            {preenchidos === 0 ? "Preencha pelo menos um campo." : `${preenchidos} campo(s) preenchido(s).`}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}

function TituloSecao({ titulo, badge, texto }: { titulo: string; badge: React.ReactNode; texto: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{titulo}</h3>
        {badge}
      </div>
      <p className="text-sm text-muted-foreground">{texto}</p>
    </div>
  )
}

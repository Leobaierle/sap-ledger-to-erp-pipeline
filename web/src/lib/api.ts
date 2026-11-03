export type PendenciaConta = {
  conta: string
  nome_sap: string
  linhas: number
  debito: number
  credito: number
  exemplo: string
}

export type PendenciaDuplicada = { conta: string; opcoes: string[] }

export type PendenciaCC = {
  cc: string
  linhas: number
  valor: number
  exemplo: string
  conta: string
}

export type Parte = {
  numero: number
  lote: number
  linhas: number
  lancamento_de: number
  lancamento_ate: number
  debito: number
  credito: number
}

export type Resultado = {
  id: string
  arquivo: string
  nome_saida: string
  pronto: boolean
  segundos: number
  periodo: [string | null, string | null]
  totais: {
    linhas_sap: number
    linhas_zeradas: number
    linhas_importar: number
    lancamentos: number
    debito: number
    credito: number
  }
  erros: string[]
  avisos: string[]
  pendencias: {
    contas: PendenciaConta[]
    duplicadas: PendenciaDuplicada[]
    centros_custo: PendenciaCC[]
  }
  maior_conta_erp: number | null
  modo: "primeira" | "complementar"
  complementar: {
    anteriores: string[]
    lanc_inicial: number
    lote_inicial: number
    linhas_ja_lancadas: number
    documentos_ja_lancados: number
    novas_em_documento_lancado: number
    linhas_sumidas: number
  } | null
  partes: Parte[]
  salvos?: string[]
}

export type Tabela = {
  campos: string[]
  rotulos: string[]
  chave: string
  obrigatorios: string[]
  linhas: Record<string, string>[]
}

export class ErroApi extends Error {
  detalhes: string[]
  constructor(mensagem: string, detalhes: string[] = []) {
    super(mensagem)
    this.detalhes = detalhes
  }
}

async function lerResposta<T>(r: Response): Promise<T> {
  const corpo = await r.json().catch(() => null)
  if (!r.ok) {
    throw new ErroApi(corpo?.erro ?? `Erro ${r.status} no servidor.`, corpo?.detalhes ?? [])
  }
  return corpo as T
}

/** Envia o razão; `aoEnviar` recebe o percentual do upload (0–100). */
export function converter(
  arquivo: File,
  opcoes: { limite?: string; lote?: string; anteriores?: File[] },
  aoEnviar: (pct: number) => void,
): Promise<Resultado> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append("razao", arquivo)
    if (opcoes.anteriores?.length) {
      form.append("modo", "complementar")
      for (const a of opcoes.anteriores) form.append("anteriores", a)
    }
    if (opcoes.limite) form.append("limite", opcoes.limite)
    if (opcoes.lote) form.append("lote", opcoes.lote)
    const xhr = new XMLHttpRequest()
    xhr.open("POST", "/api/converter")
    xhr.upload.onprogress = (e) => e.lengthComputable && aoEnviar(Math.round((e.loaded / e.total) * 100))
    xhr.onload = () => {
      let corpo: { erro?: string; detalhes?: string[] } | null = null
      try {
        corpo = JSON.parse(xhr.responseText)
      } catch {
        /* resposta não-JSON (ex.: proxy) */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(corpo as Resultado)
      else reject(new ErroApi(corpo?.erro ?? `Erro ${xhr.status} no servidor.`, corpo?.detalhes ?? []))
    }
    xhr.onerror = () => reject(new ErroApi("Não consegui falar com o servidor. Confira a rede e tente de novo."))
    xhr.send(form)
  })
}

export const buscarTrabalho = (id: string) => fetch(`/api/trabalhos/${id}`).then(lerResposta<Resultado>)

export const salvarPendencias = (
  id: string,
  corpo: {
    contas: Record<string, { conta_erp: string; nome_conta: string }>
    duplicadas: Record<string, string>
    centros_custo: Record<string, string>
  },
) =>
  fetch(`/api/trabalhos/${id}/pendencias`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  }).then(lerResposta<Resultado>)

export const urlArquivo = (id: string) => `/api/trabalhos/${id}/arquivo`

export const buscarTabela = (nome: string) => fetch(`/api/tabelas/${nome}`).then(lerResposta<Tabela>)

export const salvarLinha = (nome: string, linha: Record<string, string>) =>
  fetch(`/api/tabelas/${nome}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(linha),
  }).then(lerResposta<{ ok: boolean }>)

export const excluirLinha = (nome: string, chave: string) =>
  fetch(`/api/tabelas/${nome}/${encodeURIComponent(chave)}`, { method: "DELETE" }).then(lerResposta<{ ok: boolean }>)

// ---------------------------------------------------------------- formatação pt-BR

const fmtReais = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const fmtInteiro = new Intl.NumberFormat("pt-BR")

export const reais = (v: number) => fmtReais.format(v)
export const inteiro = (v: number) => fmtInteiro.format(v)
export const data = (iso: string | null) => (iso ? iso.split("-").reverse().join("/") : "—")

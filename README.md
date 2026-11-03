# SAP → ERP contábil: pipeline do movimento contábil

Converte o **razão do SAP** na planilha de importação do movimento contábil de um ERP contábil e **importa sozinho
toda noite**. O robô extrai do SAP por RFC, converte, importa no ERP por um robô de tela, confere o resultado pela API
do ERP e mostra tudo num portal.

> Projeto real, em produção, publicado aqui sem dados do cliente. Nomes de empresa, plano de contas, centros de custo,
> hosts e credenciais foram trocados por exemplos (`ACME`, `EMP`, `example.com`).

## O problema

A conversão era feita numa planilha de fórmulas com centenas de milhares de linhas. Ela travava e exigia colar,
fatiar em abas e conferir tudo à mão. Converter e importar **um mês levava mais de um dia de trabalho**, e cada
importação complementar repetia boa parte do esforço.

## Resultado

- Um mês com **~410 mil linhas** é convertido em **~28 s**, com **zero diferenças** em relação à planilha manual
  (regressão feita linha a linha contra meses já importados).
- A importação roda sozinha todo dia. O que precisa de atenção (conta sem
  de-para, lote que não confirmou) aparece como pendência no portal.

## Arquitetura

```
                 cron 22h / botão "Executar agora"
                              │
┌──────────┐  RFC (leitura)  ┌▼──────────────┐   planilha .xlsx   ┌──────────────────┐
│   SAP    │ ──────────────► │ robo_noturno  │ ─────────────────► │ robô de tela     │──► ERP contábil
│ BKPF/BSEG│                 │  (Python)     │                    │ (Playwright+OCR) │      │
│ FAGLFLEXA│                 │ montar razão  │ ◄───────────────── │                  │      │
└──────────┘                 │ conversor     │   eventos JSON     └──────────────────┘      │
                             │ lotes         │ ◄──────────── conferência pela API ─────────┘
                             └──────┬────────┘
                                    │ Postgres (execuções, etapas, pendências) + MinIO (arquivos)
                             ┌──────▼────────┐
                             │ Portal (React)│  login Microsoft Entra (JWT)
                             └───────────────┘
```

| Pasta | O que tem |
|---|---|
| `app/` | **Conversor** (Flask): lê o razão (`.xlsx` ou o `.xls` em texto que o SAP exporta), aplica as regras e grava a planilha de importação. `xlsx_rapido.py` grava ~800 mil linhas em ~10 s. |
| `web/` | Tela do conversor manual (React 19, Vite, Tailwind v4, shadcn/ui): envio, pendências, download, edição das tabelas de-para. |
| `sap/` | **Robô diário**: extração RFC (`extrair_razao.py`), montagem do razão, divisão em lotes, gravação e leitura pela API do ERP, fila de pedidos do portal, comparação mês a mês. |
| `sap/webgui/` | Balancete do SAP pelo SAP GUI para HTML (Playwright, só leitura): lê a lista clássica da tela e remonta o arquivo exatamente como o export manual. |
| `rpa/` | **Robô de tela** do ERP, que é um app Java servido no navegador (canvas, sem DOM): login, troca de empresa e módulo, upload e importação por coordenadas, leitura da tela por OCR. |
| `portal/` | Portal do robô (Flask + React): execuções, etapas, log, pendências, arquivos de cada noite, de-para e o botão "Executar agora". |

## Regras que valem a pena olhar

**Conversão** (`app/conversor.py`)
- O razão é lido pelo nome das colunas. Quando vem em texto, os subtotais do próprio SAP são conferidos.
- Cada partida vira uma linha no layout do ERP: D/C, data, conta (pelo plano de contas), valor, histórico, documento,
  centro de custo e filial. Linhas de valor zero saem.
- Os lançamentos são numerados e agrupados em partes de até **49.998 linhas**. Um lançamento nunca é dividido entre
  partes, e cada parte fecha **débito = crédito**.
- **Complementar:** recebe o razão já importado e o razão novo e separa só os documentos ainda não lançados. A
  numeração continua de onde parou.
- Avisa, sem bloquear: linhas que sumiram, linhas novas em documento já lançado, D ≠ C, históricos que o Excel
  confundiria com fórmula.

**Robô diário** (`sap/robo_noturno.py`)
- Janela: do dia 1 do mês até hoje. Nos primeiros dias do mês também olha o mês anterior, para pegar os lançamentos
  de fechamento (cada mês no seu lote).
- Só importa documentos ainda não importados. Conta SAP sem conta no ERP **segura o documento** e vira pendência no
  portal.
- Lote = maior lote do mês no ERP + 1 (lido pela API, nunca de memória local).
- Importação sem "Sucesso" vira **verificar**. Na execução seguinte o robô confere o lote pela API antes de qualquer
  coisa e **nunca repete no escuro**.
- Um documento só é marcado como importado depois da conferência pela API: partidas, lançamentos e D = C iguais à
  planilha.

**Robô de tela** (`rpa/scripts/importar_erp.mjs`)
- O ERP roda num canvas, então não há seletor. A automação usa coordenadas, área de transferência e OCR (`ocr.mjs`)
  para ler títulos e mensagens.
- Se o login cai em outra empresa ou módulo, o robô troca sozinho e confere pelo título.
- Nunca aperta Esc nem fecha a janela durante a importação. Em qualquer erro, para e avisa em vez de tentar de novo.
- Cada passo sai como evento JSON (`{"ev": ...}`), que o robô diário repassa ao log do portal.

## Stack

Python 3.12 (Flask, openpyxl, python-calamine, psycopg 3, PyRFC), Node 22 (Playwright, pngjs), React 19 + Vite +
Tailwind + shadcn/ui, Postgres, MinIO, Docker/Kubernetes, cron.

## Rodando localmente (só o conversor)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd web && npm ci && npm run build && cd ..
.venv/bin/python app/app.py     # http://localhost:8090 — sem DATABASE_URL usa os CSVs fictícios de app/dados/
```

O robô diário precisa de SAP, ERP, Postgres e MinIO: veja `.env.example`, `rpa/.env.example` e `portal/sql/`.

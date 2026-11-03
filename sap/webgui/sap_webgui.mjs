// SAP pelo navegador (SAP GUI para HTML / WebGUI), SÓ LEITURA. Baixa o balancete (F.01 / RFBILA00) direto
// do SAP: roda a lista clássica e lê o texto dela da tela (o download de arquivo não funciona no WebGUI deste servidor:
// as telas ITS DOWNLOAD aparecem e o arquivo nunca chega). Sai sempre do SAP no fim.
//
// Uso:
//   node sap/webgui/sap_webgui.mjs explorar PASTA [TRANSACAO]   entra, abre a transação (padrão F.01), prints + campos
//   node sap/webgui/sap_webgui.mjs balancete PASTA AAAAMM       F.01: empresa 1200, estrutura ZB03, PT, períodos 1 até o
//                                                               mês, comparação ano anterior 1–16, lista clássica →
//                                                               PASTA/lista.json (campos de cada linha da lista);
//                                                               sap/webgui/lista_para_txt.py monta o .xls "não convertido"
// Precisa: acesso ao SAP (VPN/túnel em 127.0.0.1:44321) e ~/.contabil-sap-gui
// (SAP_GUI_USER, SAP_GUI_PASS, SAP_GUI_MANDANTE). Aviso de login múltiplo = para sem escolher nada.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { chromium } from 'playwright';

const [modo, PASTA, ARG] = process.argv.slice(2);
if (!['explorar', 'balancete'].includes(modo) || !PASTA || (modo === 'balancete' && !/^\d{6}$/.test(ARG || ''))) {
  console.error('uso: sap_webgui.mjs explorar PASTA [TRANSACAO] | balancete PASTA AAAAMM');
  process.exit(2);
}
fs.mkdirSync(PASTA, { recursive: true });
const E = Object.fromEntries(fs.readFileSync(path.join(os.homedir(), '.contabil-sap-gui'), 'utf8').split('\n')
  .filter((l) => l.includes('=')).map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]));
const URL = 'https://127.0.0.1:44321/sap/bc/gui/sap/its/webgui';

let n = 0;
const log = (o) => console.log(JSON.stringify({ quando: new Date().toISOString(), ...o }));
async function print(page, nome) {
  const f = path.join(PASTA, `${String(++n).padStart(2, '0')}-${nome}.png`);
  await page.screenshot({ path: f });
  log({ print: f });
}
// a tela do SAP fica num iframe: o quadro que tem o campo de comando (ou o que tiver mais campos)
const OKCD = 'input[id*="okcd" i], input[title*="omando"], input[title*="ransa"], input[name*="okcd" i]';
async function tela(page) {
  let melhor = page.mainFrame(), max = -1;
  for (const f of page.frames()) {
    if (await f.locator(OKCD).count().catch(() => 0)) return f;
    const k = await f.locator('input:not([type=hidden])').count().catch(() => 0);
    if (k > max) { max = k; melhor = f; }
  }
  return melhor;
}
async function comando(page, texto) {
  const f = await tela(page);
  const ok = f.locator(OKCD).first();
  if (!(await ok.count())) throw new Error('campo de comando não achado');
  await ok.fill(texto);
  await ok.press('Enter');
}
async function textoTela(page) {
  return (await (await tela(page)).locator('body').innerText()).replace(/\s+/g, ' ');
}
async function campos(page, nome) {
  const lista = await (await tela(page)).$$eval('input, select, textarea', (is) => is.filter((i) => i.type !== 'hidden')
    .map((i) => ({ id: i.id, name: i.name, tipo: i.type, valor: i.type === 'password' ? '' : i.value,
                   rotulo: (i.labels?.[0]?.innerText || i.title || '').trim().slice(0, 60) })));
  fs.writeFileSync(path.join(PASTA, `${nome}-campos.json`), JSON.stringify(lista, null, 1));
  log({ campos: nome, total: lista.length });
  return lista;
}
// preenche o k-ésimo campo de texto com esse rótulo (0 = "de", 1 = "até")
async function preencher(page, rotulo, valor, k = 0) {
  const f = await tela(page);
  const ids = await f.$$eval('input[type=text], input:not([type])', (is, r) => is
    .filter((i) => (i.labels?.[0]?.innerText || i.title || '').trim() === r).map((i) => i.id), rotulo);
  if (!ids[k]) throw new Error(`campo "${rotulo}" (${k}) não achado`);
  const c = f.locator(`[id="${ids[k]}"]`);
  await c.fill(valor);
  log({ campo: rotulo, k, valor });
}
// janelas (popups) do WebGUI ficam em outro iframe: procura o texto em todos os quadros
async function quadroCom(page, re) {
  for (const f of page.frames()) {
    const t = await f.locator('body').innerText({ timeout: 3000 }).catch(() => '');
    if (re.test(t.replace(/\s+/g, ' '))) return f;
  }
  return null;
}
async function esperarTexto(page, re, ms = 60000) {
  const fim = Date.now() + ms;
  while (Date.now() < fim) {
    const f = await quadroCom(page, re);
    if (f) return f;
    await page.waitForTimeout(1500);
  }
  return null;
}
const JANELAS = /Gravar lista em file|Salvar como|Fazer download|Transferir|Nome file|ITS QUERY/i;
async function fecharJanelas(page) {
  for (let i = 0; i < 3; i++) {
    const f = await quadroCom(page, JANELAS);
    if (!f) return;
    const x = f.locator('[title*="Cancelar"], [title*="Fechar"], [title*="Close"]').first();
    if (await x.count()) await x.click({ noWaitAfter: true }).catch(() => {});
    else await page.keyboard.press('Escape');
    await page.waitForTimeout(2500);
  }
}
async function clicarTexto(page, texto) {
  await (await tela(page)).getByText(texto, { exact: true }).first().click();
  await page.waitForTimeout(3000);
}
// espera o SAP terminar o processamento (sem "aguarde"/indicador) e devolve o texto da tela
async function esperarSap(page, ms = 600000) {
  const fim = Date.now() + ms;
  while (Date.now() < fim) {
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
    const t = await textoTela(page).catch(() => '');
    if (t && !/aguarde|processando|em execução/i.test(t)) return t;
    await page.waitForTimeout(3000);
  }
  throw new Error('SAP não terminou o processamento');
}

async function balancete(page, aaaamm) {
  const ano = aaaamm.slice(0, 4), mes = String(Number(aaaamm.slice(4)));
  await comando(page, '/nF.01');
  for (let i = 0; i < 30 && !/Estrutura de balanço\/DRE/.test(await textoTela(page).catch(() => '')); i++) {
    await page.waitForTimeout(2000);
  }
  await esperarSap(page);
  await preencher(page, 'Empresa', '1200');
  await preencher(page, 'Estrutura de balanço/DRE', 'ZB03');
  await preencher(page, 'Código de idioma', 'PT');
  await preencher(page, 'Exercício', ano, 0);
  await preencher(page, 'Intervalo para a delimitação de períodos de relatório', '1', 0);
  await preencher(page, 'Intervalo para a delimitação de períodos de relatório', mes, 1);
  await preencher(page, 'Exercício', String(Number(ano) - 1), 1);
  await preencher(page, 'Meses de comparação', '1', 0);
  await preencher(page, 'Meses de comparação', '16', 1);
  await print(page, 'f01-preenchida');
  for (const aba of ['Análises especiais', 'Controle de saída']) {
    await clicarTexto(page, aba);
    await print(page, `aba-${aba.replace(/\s+/g, '-')}`);
    await campos(page, `aba-${aba.replace(/\s+/g, '-')}`);
  }
  await clicarTexto(page, 'Outras delimitações');
  const lc = await (await tela(page)).getByText('Lista clássica', { exact: true }).count();
  if (lc) await clicarTexto(page, 'Lista clássica');
  await print(page, 'antes-executar');
  const t0 = Date.now();
  // Executar = F8 (o clique no botão não chega ao SAP no WebGUI)
  await (await tela(page)).locator(OKCD).first().focus();
  await page.keyboard.press('F8');
  await page.waitForTimeout(5000);
  let t = await esperarSap(page);
  // sem /i: a tela de seleção tem "Estrutura de balanço/DRE" e casava antes da lista existir (falha de 20/10 22h)
  for (let i = 0; i < 120 && !/ESTRUTURA DE BALAN/.test(t); i++) {
    if (/obrigat|erro|não existe|inválid/i.test(t.slice(-300))) break;
    await page.waitForTimeout(5000);
    t = await textoTela(page);
  }
  await print(page, 'lista');
  log({ executou_em_s: Math.round((Date.now() - t0) / 1000), tela: t.slice(0, 300) });
  if (!/ESTRUTURA DE BALAN/.test(t)) throw new Error(`a lista do balancete não apareceu: "${t.slice(-300)}"`);
  await capturarLista(page, path.join(PASTA, 'lista.json'));
}

// Lê a lista inteira da tela: cabeçalho fixo (linhas 0–7 da tela) + corpo rolando com P+. Cada campo vem com a coluna
// (lbl[col,linha]) e o texto exato do SAP; as linhas verticais vêm como imagem. Grava {total, cabecalho, linhas}.
async function lerTela(page) {
  const f = await tela(page);
  return f.$eval('[ct="AL"]', (al) => ({ al: al.getAttribute('lsdata'),
    itens: [...al.querySelectorAll('[lsdata]')].map((e) => e.getAttribute('lsdata')) }));
}
const numAL = (al, k) => Number((al.match(new RegExp(`[{,]${k}:([\\d.]+)`)) || [])[1]);
async function capturarLista(page, destino) {
  let t = await lerTela(page);
  const total = numAL(t.al, 4), visiveis = numAL(t.al, 6);
  const telas = [];
  for (let i = 0; i < 200; i++) {
    const primeira = numAL(t.al, 5);
    telas.push({ primeira, itens: t.itens });
    if (primeira + visiveis > total) break;
    await comando(page, 'P+');
    let nova = t;
    for (let k = 0; k < 40 && numAL(nova.al, 5) === primeira; k++) {
      await page.waitForTimeout(500);
      nova = await lerTela(page).catch(() => nova);
    }
    if (numAL(nova.al, 5) === primeira) throw new Error(`a lista não rolou depois da linha ${primeira}`);
    t = nova;
  }
  fs.writeFileSync(destino, JSON.stringify({ total, visiveis, telas }, null, 0));
  log({ lista: destino, total, telas: telas.length, ultima_primeira: telas.at(-1).primeira });
}

const browser = await chromium.launch();
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';
const ctx = await browser.newContext({ ignoreHTTPSErrors: true, acceptDownloads: true, userAgent: UA,
                                       viewport: { width: 1400, height: 950 }, locale: 'pt-BR' });
const page = await ctx.newPage();
page.setDefaultTimeout(15000);
let entrou = false;
try {
  await page.goto(`${URL}?sap-language=PT&sap-client=${E.SAP_GUI_MANDANTE || '800'}`, { timeout: 90000 });
  await page.fill('input[name="sap-user"]', E.SAP_GUI_USER);
  await page.fill('input[name="sap-password"]', E.SAP_GUI_PASS);
  const mandante = page.locator('input[name="sap-client"]');
  if (await mandante.count()) await mandante.fill(E.SAP_GUI_MANDANTE || '800');
  await Promise.all([page.waitForLoadState('networkidle', { timeout: 90000 }).catch(() => {}),
                     page.keyboard.press('Enter')]);
  await page.waitForTimeout(5000);
  await print(page, 'depois-login');
  const texto = await textoTela(page);
  log({ tela: texto.slice(0, 200) });
  if (/login múltiplo|logon múltiplo|multiple logon/i.test(texto)) {
    throw new Error('aviso de login múltiplo: alguém já está logado com este usuário; parado sem escolher nada');
  }
  if (await page.locator('input[name="sap-user"]').count()) throw new Error('login recusado (ver print depois-login)');
  entrou = true;
  if (modo === 'explorar') {
    const tr = ARG || 'F.01';
    await comando(page, `/n${tr}`);
    await page.waitForTimeout(6000);
    await print(page, `transacao-${tr}`);
    await campos(page, `transacao-${tr}`);
  } else {
    await balancete(page, ARG);
  }
} catch (e) {
  log({ erro: String(e).slice(0, 500) });
  await print(page, 'erro').catch(() => {});
  process.exitCode = 1;
} finally {
  if (entrou) {
    try {   // sair sempre: /nex encerra a sessão sem perguntar (nada foi alterado). Janela aberta (ex.: Gravar lista)
            // bloqueia o campo de comando: fecha com Esc (= Cancelar) e tenta de novo; último recurso, Efetuar logoff › Sim
      let saiu = false;
      for (let i = 0; i < 4 && !saiu; i++) {
        await page.waitForTimeout(2000);
        await fecharJanelas(page);
        await comando(page, '/nex').catch(() => {});
        await page.waitForTimeout(4000);
        saiu = /efetuou logoff|logoff do sistema/i.test(await page.locator('body').innerText().catch(() => ''));
      }
      if (!saiu) {
        await clicarTexto(page, 'Efetuar logoff').catch(() => {});
        await clicarTexto(page, 'Sim').catch(() => {});
        await page.waitForTimeout(4000);
        saiu = /efetuou logoff|logoff do sistema/i.test(await page.locator('body').innerText().catch(() => ''));
      }
      await print(page, 'saida');
      log({ saiu });
    } catch (e) { log({ erro_saida: String(e).slice(0, 300) }); }
  }
  await browser.close();
}

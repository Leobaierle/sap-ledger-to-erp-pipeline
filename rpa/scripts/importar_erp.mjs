// Importador automático da ERP (robô noturno da ACME): envia as planilhas pela Transferência de arquivos e importa
// uma a uma em 5 › 2 › I, conferindo a TELA (OCR com tesseract + pixels) antes de cada clique.
//
// Uso: node rpa/scripts/importar_erp.mjs PEDIDO.json
//   PEDIDO.json = { "pasta": "<onde salvar prints>", "ensaio": false,
//                   "arquivos": [ { "arquivo": "/caminho/CONTABIL_1000005_202610182200.xlsx", "de": "01102026", "ate": "18102026" } ] }
// Escreve uma linha JSON por evento no stdout ({"ev": ..., ...}). Código de saída:
//   0  todos os arquivos com "Sucesso"
//   10 parou ANTES de confirmar qualquer importação desta rodada pendente (nada gravado no arquivo da vez)
//   11 login recusado (sessão do robo-importa ainda aberta, ou a ERP Cloud recusou a senha): nada foi feito, dá para
//      tentar de novo mais tarde
//   20 INCERTO: depois do "Sim" não houve "Sucesso" (verificar na ERP; nunca repetir sozinho)
// Regras (README.md): nunca repete importação; nunca aperta Esc nem fecha durante a importação; sai sempre por
// ☰ › S-Sair e confere "The application has been closed"; tela diferente da esperada = para.
// Ensaio: faz tudo até o "Confirma?" e responde Não (nada é importado).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { ocr, px, digitos } from './ocr.mjs';

const RPA = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PEDIDO = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const PASTA = PEDIDO.pasta;
fs.mkdirSync(PASTA, { recursive: true });

const E = {};
for (const linha of fs.readFileSync(path.join(RPA, '.env'), 'utf8').split('\n')) {
  const m = linha.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
  if (m) E[m[1]] = m[2];
}
// pasta do servidor de arquivos do ERP onde a planilha é enviada antes da importação
const AUTOMACAO = E.ERP_PASTA_AUTOMACAO || '/SHARED/AUTOMACAO/';

const ev = (o) => console.log(JSON.stringify({ quando: new Date().toISOString(), ...o }));
class Parar extends Error { constructor(msg, codigo = 10) { super(msg); this.codigo = codigo; } }

let page, browser, n = 0, emImportacao = false;   // true entre o "Sim" e o "Sucesso": não pode sair nem fechar
const espera = (ms) => page.waitForTimeout(ms);

async function snap(nome) {
  n++;
  const f = path.join(PASTA, `${String(n).padStart(3, '0')}-${nome}.png`);
  await page.screenshot({ path: f });
  return f;
}

// espera até a tela ter TODAS as palavras no recorte (ou estourar o tempo)
async function ate(nome, regiao, palavras, { tempo = 30000, passo = 2000 } = {}) {
  const fim = Date.now() + tempo;
  let f, t = '';
  while (Date.now() < fim) {
    f = await snap(nome);
    t = ocr(f, regiao);
    if (palavras.every((p) => t.includes(p))) return { f, t };
    await espera(passo);
  }
  throw new Parar(`tela "${nome}" não apareceu (esperava ${palavras.join(', ')}; li: "${t.slice(0, 160)}") — ${f}`);
}

const TITULO = [0, 0, 1000, 22];
const MODULO = [40, 45, 200, 72];

// 26–27/10: alguém usou o robo-importa em outra empresa/módulo (FBE, Livros Fiscais) e o ERP abre onde a última sessão
// parou. Troca uma vez para o módulo Contabilidade (Barra de módulos) e a empresa EMP (⇄ › Troca de empresa); se a tela
// não confirmar cada passo, para.
async function irParaMsc(f) {
  if (!ocr(f, MODULO).includes('contab')) {
    await page.mouse.click(1410, 89);                    // Barra de módulos (abre a faixa com os módulos)
    await espera(2500);
    await ate('barra-modulos', [5, 109, 100, 125], ['contab'], { tempo: 10000 });
    await page.mouse.click(55, 117);                     // Contabilidade
    await ate('modulo-contabilidade', MODULO, ['contab'], { tempo: 30000 });
    await page.mouse.click(1410, 89);                    // fecha a faixa (senão a tela desce 27 px e os cliques erram)
    await espera(2500);
    const g = await snap('barra-fechada');
    if (ocr(g, [5, 109, 100, 125]).includes('contab')) throw new Parar(`a Barra de módulos não fechou — ${g}`);
    ev({ ev: 'módulo trocado para Contabilidade', print: g });
    f = g;
  }
  if (!ocr(f, TITULO).includes('empresa-acme')) {
    await page.mouse.click(25, 30);                      // ⇄ ao lado de "Empresa:"
    await ate('troca-empresa', [516, 275, 1084, 295], ['troca de empresa'], { tempo: 15000 });
    // 28–29/10: a janela abriu em Raz. Social (fica salvo por usuário) e aí a sigla colada não busca a empresa
    await espera(1500);
    let r = await snap('troca-empresa-radio');
    if (px(r, 541, 392).join() !== '255,255,255') {
      await page.mouse.click(541, 392);                  // rádio Sigla
      await espera(1500);
      r = await snap('troca-empresa-radio-sigla');
      if (px(r, 541, 392).join() !== '255,255,255') throw new Parar(`Troca de empresa: não consegui marcar Sigla — ${r}`);
      ev({ ev: 'troca de empresa: estava em Raz. Social, marcou Sigla', print: r });
    }
    await page.mouse.click(645, 391);                    // campo Sigla
    await espera(600);
    await page.keyboard.press('Control+A');
    await page.evaluate((t) => navigator.clipboard.writeText(t), 'EMP');
    await page.keyboard.press('Control+V');
    await espera(2000);
    const g = await snap('troca-empresa-msc');
    if (!ocr(g, [624, 404, 1074, 422]).includes('contabil')) {
      await page.mouse.click(924, 643);                  // Cancelar
      throw new Parar(`Troca de empresa: a sigla EMP não trouxe a ACME ("${ocr(g, [624, 404, 1074, 422])}") — ${g}`);
    }
    await page.mouse.click(1023, 643);                   // OK (Enter vaza para a tela de fundo)
    const { f: h } = await ate('empresa-msc', TITULO, ['empresa-acme'], { tempo: 30000 });
    ev({ ev: 'empresa trocada para EMP', print: h });
  }
}

async function login() {
  for (let i = 0; i < 3; i++) {
    try {
      await page.goto(E.ERP_URL, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForSelector('#nameInput', { timeout: 30000 });
      break;
    } catch (e) {
      if (i === 2) throw new Parar(`não carregou a tela de login do Webswing: ${String(e).slice(0, 120)}`);
      await espera(5000);
    }
  }
  await page.fill('#nameInput', E.ERP_USER1);
  await page.fill('#passwordInput', E.ERP_PASS1);
  await page.click('#loginFormSubmitButton');
  try {
    await ate('login-erp', [600, 440, 1000, 570], ['senha'], { tempo: 120000, passo: 5000 });
  } catch (e) {
    // 22/10: a ERP Cloud recusou a credencial certa ("Invalid Username or Password") e no dia seguinte aceitou:
    // falha passageira, mesmo tratamento da sessão presa (nada foi feito, tenta de novo mais tarde)
    if (String(e.message).includes('invalid username')
        || await page.getByText('Invalid Username or Password', { exact: false }).count().catch(() => 0)) {
      throw new Parar(`login recusado pela ERP Cloud ("Invalid Username or Password") — ${path.join(PASTA, String(n).padStart(3, '0'))}-login-erp.png`, 11);
    }
    throw e;
  }
  ev({ ev: 'webswing ok' });
  for (const [x, valor] of [[700, E.ERP_USER2], [888, E.ERP_PASS2]]) {
    await page.mouse.click(x, 538);                      // campo Usuário / Senha
    await espera(800);
    await page.keyboard.press('Control+A');
    await page.evaluate((t) => navigator.clipboard.writeText(t), valor);
    await page.keyboard.press('Control+V');
    await espera(1200);
  }
  await page.keyboard.press('Enter');
  await espera(1500);
  // tela principal: título com a empresa EMP e o usuário robo-importa; diálogo claro no meio = sessão já aberta
  let fim = Date.now() + 90000;
  let trocou = false;
  while (Date.now() < fim) {
    await espera(5000);
    const f = await snap('login-resultado');
    // aviso "Novidades" depois de atualização do ERP (aparece uma vez por versão): responde Não e segue
    if (ocr(f, [596, 342, 1010, 582]).includes('novidades') || ocr(f, [596, 342, 1010, 582]).includes('foi atualizado')) {
      await page.mouse.click(961, 561);                  // Não
      ev({ ev: 'aviso de novidades do ERP respondido com Não', print: f });
      continue;
    }
    const meio = px(f, 800, 460);
    if (meio[0] > 200 && meio[1] > 200 && meio[2] > 200 && !ocr(f, TITULO).includes('msc')) {
      throw new Parar(`apareceu um aviso no login (provável sessão ainda aberta): "${ocr(f, [560, 330, 1040, 600]).slice(0, 200)}" — ${f}`);
    }
    const t = ocr(f, TITULO);
    if (Date.now() > fim - 60000 && ocr(f, [600, 440, 1000, 570]).includes('senha')) {
      throw new Parar(`login recusado: a ERP voltou para a tela de login (provável sessão do robo-importa ainda aberta) — ${f}`, 11);
    }
    const certo = t.includes('empresa-acme') && ocr(f, MODULO).includes('contab');
    if (certo && t.includes('ctb')) {
      ev({ ev: 'login ok', print: f });
      return;
    }
    if (t.includes('[') && t.includes('usu') && !certo) {
      if (trocou) throw new Parar(`continua fora da EMP/Contabilidade depois da troca: "${t.slice(0, 160)}" — ${f}`);
      ev({ ev: 'entrou em outra empresa/módulo, trocando para EMP/Contabilidade', titulo: t.slice(0, 160), print: f });
      await irParaMsc(f);
      trocou = true;
      fim = Math.max(fim, Date.now() + 60000);
    }
  }
  throw new Parar('não chegou à tela principal da Contabilidade/EMP em 90 s');
}

async function enviar(arquivo) {
  const nome = path.basename(arquivo);
  await page.mouse.click(555, 59);                       // 8º ícone: Transferência de arquivos (Shift+F9)
  await ate('transferencia', [460, 130, 1140, 215], ['diretorio', 'empresa_msc', 'automa']);
  await page.mouse.click(510, 259);                      // Upload
  await ate('open-file', [640, 330, 960, 440], ['open file']);
  await espera(3000);                                    // a janela do Webswing ainda está aparecendo (animação)
  let entregue = false;
  const campoArquivo = page.locator('input[type=file]');
  if (await campoArquivo.count().catch(() => 0)) {
    await campoArquivo.first().setInputFiles(arquivo).then(() => { entregue = true; }).catch(() => {});
  }
  for (let i = 0; i < 3 && !entregue; i++) {
    try {
      const [fc] = await Promise.all([page.waitForEvent('filechooser', { timeout: 10000 }), page.mouse.click(720, 520)]);
      await fc.setFiles(arquivo);
      entregue = true;
    } catch { await espera(2000); }
  }
  if (!entregue) throw new Parar('o "Browse" do Upload não abriu o seletor de arquivo');
  await espera(8000);
  // confere o arquivo na lista: os dígitos do nome (lote + carimbo de data/hora) têm que aparecer.
  // 31/10: a pasta encheu e o arquivo novo ficou na última linha, cortada/rolada para fora do recorte → filtra a lista
  // pelo nome no "Digite aqui para buscar..." em vez de ler a pasta inteira
  const [, lote, carimbo] = nome.match(/_(\d+)_(\d+)\./) || [];
  let achou = false, f;
  for (let i = 0; i < 4 && !achou; i++) {
    await page.mouse.click(573, 204);
    await espera(3000);
    await page.mouse.click(695, 753);                    // busca da lista
    await espera(400);
    await page.keyboard.press('Control+A');
    await page.keyboard.press('Backspace');
    await page.keyboard.type(`${lote}_${carimbo}`, { delay: 40 });
    await espera(2000);
    f = await snap('transferencia-lista');
    const d = digitos(ocr(f, [608, 230, 985, 252]));       // filtrada: o arquivo é a 1ª linha (recorte grande e vazio = OCR em branco)
    achou = !!lote && d.includes(lote) && d.includes(carimbo.slice(-6));
  }
  await page.mouse.click(978, 787);                      // Cancelar (fecha a janela; o arquivo já está no servidor)
  await espera(1500);
  if (!achou) throw new Parar(`o arquivo ${nome} não apareceu na pasta AUTOMAÇÃO depois do upload — ${f}`);
  ev({ ev: 'enviado', arquivo: nome, print: f });
}

async function abrirImportacao() {
  for (let tentativa = 1; tentativa <= 2; tentativa++) {
    for (let i = 0; i < 3; i++) { await page.keyboard.press('Escape'); await espera(400); }
    await page.mouse.click(621, 89);                     // 5-Rot.Especiais
    await espera(1500);
    await page.mouse.click(700, 156);                    // 2-Importação/Exportação de movimentos
    await espera(1500);
    let f = await snap('menu');
    if (!ocr(f, [843, 141, 1194, 330]).includes('arquivo xls')) continue;
    await page.mouse.click(987, 270);                    // I-Importação de lançamentos via arquivo XLS
    try {
      await ate('form-importacao', [334, 285, 1265, 305], ['contab', 'msc'], { tempo: 15000 });
      return;
    } catch (e) { if (tentativa === 2) throw e; }
  }
  throw new Parar('não abriu 5 › 2 › I (importação via arquivo XLS)');
}

async function importar({ arquivo, de, ate: ateData }) {
  const nome = path.basename(arquivo);
  await abrirImportacao();
  // 20/10: o Control+A não pegou e o caminho foi colado no meio do que já estava no campo ("…/CTE/Empresa/SHARED/…"),
  // a ERP recusou a pasta. Agora seleciona com End + Shift+Home e, se vier "Localização inexistente", fecha e repete.
  const campo = async (x, y, valor) => {
    await page.mouse.click(x, y); await espera(800);
    await page.keyboard.press('End'); await espera(200);
    await page.keyboard.press('Shift+Home'); await espera(300);
    await page.evaluate((t) => navigator.clipboard.writeText(t), valor);
    await page.keyboard.press('Control+V'); await espera(600);
    await page.keyboard.press('Tab'); await espera(1500);
  };
  for (let tentativa = 1; ; tentativa++) {
    await campo(860, 358, AUTOMACAO);
    const fp = await snap('form-pasta');
    const alerta = ocr(fp, [578, 338, 1024, 562]);
    if (!['inexist', 'inacess', 'aten'].some((p) => alerta.includes(p))) break;
    if (tentativa === 3) throw new Parar(`a ERP recusou a pasta AUTOMAÇÃO 3 vezes: "${alerta.slice(0, 200)}" — ${fp}`);
    ev({ ev: 'pasta recusada, tentando de novo', tentativa, print: fp });
    await page.mouse.click(974, 541); await espera(1500);  // OK do "Localização inexistente ou inacessível"
  }
  await campo(860, 380, nome);
  for (const [x, valor] of [[612, de], [845, ateData]]) {
    await page.mouse.click(x, 424); await espera(300);
    await page.keyboard.press('Home');
    await page.keyboard.type(valor, { delay: 110 });
  }
  await page.keyboard.press('Tab'); await espera(1000);
  let f = await snap('form-preenchido');
  const t = ocr(f, [596, 348, 1130, 432]);
  const ok = t.includes('automa') && digitos(t).includes(digitos(nome).slice(0, 7))
    && t.includes('contabil') && t.includes(`${de.slice(0, 2)}/${de.slice(2, 4)}/${de.slice(4)}`)
    && t.includes(`${ateData.slice(0, 2)}/${ateData.slice(2, 4)}/${ateData.slice(4)}`);
  if (!ok) throw new Parar(`formulário diferente do esperado: "${t}" — ${f}`);
  await page.mouse.click(1203, 632);                     // Avançar
  await espera(6000);
  f = await snap('confirma');
  const amarelo = px(f, 800, 693);
  if (!(amarelo[0] > 240 && amarelo[1] > 200 && amarelo[2] < 80) || !ocr(f, [650, 660, 950, 730]).includes('confirma')) {
    throw new Parar(`não apareceu o "Confirma?" (a ERP respondeu: "${ocr(f, [560, 330, 1040, 600]).slice(0, 200)}") — ${f}`);
  }
  if (PEDIDO.ensaio) {
    await page.mouse.click(799, 769);                    // Não
    await espera(2000);
    await page.mouse.click(1103, 632);                   // Cancelar o formulário
    await espera(1500);
    ev({ ev: 'ensaio: parou no Confirma?', arquivo: nome, print: f });
    return;
  }
  emImportacao = true;
  await page.mouse.click(709, 769);                      // Sim — daqui em diante, nada de Esc/fechar
  ev({ ev: 'importando', arquivo: nome });
  const fim = Date.now() + 6 * 3600 * 1000;
  let semJanela = 0;
  while (Date.now() < fim) {
    await espera(30000);
    f = await snap('progresso');
    const meio = ocr(f, [520, 330, 1080, 620]);
    if (meio.includes('sucesso') && meio.includes('importa')) {
      await page.mouse.click(902, 528);                  // OK
      emImportacao = false;
      await espera(1500);
      ev({ ev: 'sucesso', arquivo: nome, print: f });
      return;
    }
    if (meio.includes('aguarde') || meio.includes('processando') || meio.includes('gravando') || meio.includes('lidos')) { semJanela = 0; continue; }
    if (meio.includes('aten') || meio.includes('erro') || meio.includes('inconsist')) {
      throw new Parar(`a ERP mostrou uma mensagem depois do "Sim": "${meio.slice(0, 240)}" — ${f}`, 20);
    }
    if (++semJanela >= 6) throw new Parar(`sem janela de progresso nem "Sucesso" há 3 min — ${f}`, 20);
  }
  throw new Parar('a importação passou de 6 h sem "Sucesso"', 20);
}

async function sair(podeFechar) {
  // nunca durante a importação (podeFechar = false depois de um "Sim" sem "Sucesso": deixa como está)
  if (!podeFechar) return false;
  // fecha o que estiver aberto por cima: janela "OPEN FILE" (HTML do Webswing) e a Transferência de arquivos
  if (await page.getByText('Please select a file', { exact: false }).count().catch(() => 0)) {
    await page.getByText('Cancel', { exact: true }).click({ timeout: 3000 }).catch(() => page.mouse.click(880, 520));
    await espera(2000);
  }
  let f0 = await snap('antes-de-sair');
  if (ocr(f0, [596, 342, 1010, 582]).includes('novidades')) { await page.mouse.click(961, 561); await espera(3000); f0 = await snap('antes-de-sair'); }
  if (ocr(f0, [460, 130, 1140, 215]).includes('diretorio')) { await page.mouse.click(978, 787); await espera(1500); }
  for (let i = 0; i < 3; i++) { await page.keyboard.press('Escape').catch(() => {}); await espera(400); }
  // 20/10: depois de fechar o formulário o menu 5-Rot.Especiais ficou aberto e o ☰ não abriu; por isso mais tentativas
  for (let tentativa = 0; tentativa < 4; tentativa++) {
    await page.mouse.click(25, 58);                      // ☰
    await espera(1500);
    const f = await snap('menu-sair');
    if (ocr(f, [30, 195, 270, 215]).includes('sair')) {
      await page.mouse.click(72, 205);                   // S-Sair
      break;
    }
    for (let i = 0; i < 2; i++) { await page.keyboard.press('Escape'); await espera(600); }
    if (tentativa === 1) { await page.mouse.click(800, 820); await espera(800); }   // clique na área vazia fecha menu
  }
  for (let i = 0; i < 10; i++) {
    await espera(2000);
    if (await page.getByText('The application has been closed', { exact: false }).count().catch(() => 0)) {
      await page.getByText('Sign out', { exact: false }).click({ timeout: 3000 }).catch(() => {});
      await espera(2000);
      ev({ ev: 'saiu da ERP', print: await snap('saiu') });
      return true;
    }
  }
  ev({ ev: 'AVISO: não confirmei a saída da ERP (sessão pode ficar presa ~30 min)', print: await snap('sem-saida') });
  return false;
}

let codigo = 0;
try {
  browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, permissions: ['clipboard-read', 'clipboard-write'] });
  page = await ctx.newPage();
  await login();
  for (const a of PEDIDO.arquivos) await enviar(a.arquivo);
  for (const a of PEDIDO.arquivos) await importar(a);
} catch (e) {
  // antes do "Sim" nada foi gravado (10/11); depois do "Sim" sem "Sucesso" é incerto (20)
  codigo = emImportacao ? 20 : (e instanceof Parar ? e.codigo : 10);
  ev({ ev: 'parou', codigo, motivo: String(e.message || e).slice(0, 600) });
}
const podeFechar = !emImportacao;
try { await sair(podeFechar); } catch (e) { ev({ ev: 'erro ao sair', motivo: String(e).slice(0, 200) }); }
if (podeFechar) await browser?.close().catch(() => {});
else {
  ev({ ev: 'navegador mantido aberto 6 h (importação pode estar rodando)' });
  await page.waitForTimeout(6 * 3600 * 1000).catch(() => {});
}
process.exit(codigo);

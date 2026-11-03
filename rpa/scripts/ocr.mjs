// OCR (tesseract) de um recorte de print: usado pelo importador para conferir a tela antes de cada clique.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { PNG } from 'pngjs';

export function px(arquivo, x, y) {
  const png = PNG.sync.read(fs.readFileSync(arquivo));
  const i = (png.width * y + x) * 4;
  return [png.data[i], png.data[i + 1], png.data[i + 2]];
}

// recorte (x0, y0, x1, y1) ampliado 3x; devolve o texto em minúsculas, espaços normalizados
export function ocr(arquivo, [x0, y0, x1, y1]) {
  const src = PNG.sync.read(fs.readFileSync(arquivo));
  const k = 3, w = (x1 - x0) * k, h = (y1 - y0) * k;
  const out = new PNG({ width: w, height: h });
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const si = (src.width * (y0 + Math.floor(y / k)) + x0 + Math.floor(x / k)) * 4, di = (w * y + x) * 4;
    for (let c = 0; c < 4; c++) out.data[di + c] = src.data[si + c];
  }
  const tmp = path.join(os.tmpdir(), `ocr-${process.pid}-${Date.now()}.png`);
  fs.writeFileSync(tmp, PNG.sync.write(out));
  const r = spawnSync('tesseract', [tmp, '-', '--psm', '6', '-l', 'eng'], { encoding: 'utf8' });
  fs.rmSync(tmp, { force: true });
  return (r.stdout || '').toLowerCase().replace(/\s+/g, ' ').trim();
}

export const digitos = (t) => t.replace(/[^0-9]/g, '');

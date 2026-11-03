"""Grava na ERP, em ordem, os lotes de uma pasta do montar_lotes.py, um por vez, com o gravar_lote.py.

Uso: gravar_sequencia.py PASTA PRIMEIRO ULTIMO

- Se a ERP recusar o lote porque uma conta "está configurada para não informar rateio de centro de custo", tira o
  centro de custo das partidas dessa conta (a importação por planilha faz isso sozinha), anota a conta em
  contas_sem_rateio.json (o montar_lotes.py passa a respeitar) e reenvia. A ERP valida o lote inteiro antes de
  gravar: nessa recusa nada foi gravado (o gravar_lote.py confere pela leitura).
- Lote conferido: marca os documentos como importados no banco do portal (robo_banco.py importado).
- Qualquer outro erro, ou lote que não confere na leitura: PARA.
"""
import json
import os
import re
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
LISTA = os.path.join(AQUI, "contas_sem_rateio.json")
RE_SEM_RATEIO = re.compile(r"A conta [\d.]*?(\d+) .*?configurada para não informar rateio de centro de custo")


def sem_rateio():
    return set(json.load(open(LISTA))) if os.path.exists(LISTA) else set()


def tirar_rateio(caminho, contas):
    corpo = json.load(open(caminho))
    n = 0
    for e in corpo["payload"]["accountingEntry"]:
        if e["account"] in contas and e.pop("costCenters", None) is not None:
            n += 1
    json.dump(corpo, open(caminho, "w"), ensure_ascii=False)
    return n


def main():
    pasta, primeiro, ultimo = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    for lote in range(primeiro, ultimo + 1):
        caminho = os.path.join(pasta, f"lote_{lote}.json")
        if not os.path.exists(caminho):
            continue
        print(f"\n=== lote {lote} — sem rateio: {tirar_rateio(caminho, sem_rateio())} partida(s)", flush=True)
        for tentativa in range(1, 80):
            p = subprocess.run([sys.executable, os.path.join(AQUI, "gravar_lote.py"), caminho, "--enviar"],
                               capture_output=True, text=True)
            saida = p.stdout + p.stderr
            print(saida.strip(), flush=True)
            if p.returncode == 0:
                r = subprocess.run([sys.executable, os.path.join(AQUI, "..", "robo_banco.py"), "importado", pasta,
                                    str(lote)], capture_output=True, text=True)
                print((r.stdout + r.stderr).strip(), flush=True)
                if r.returncode != 0:
                    sys.exit(f"PARADO: lote {lote} gravado e conferido na ERP, mas não marcado no banco do portal.")
                break
            m = RE_SEM_RATEIO.search(saida)
            if not m or "não aparece na leitura" not in saida:
                sys.exit(f"PARADO no lote {lote} (tentativa {tentativa}).")
            conta = int(m.group(1))
            lista = sem_rateio() | {conta}
            json.dump(sorted(lista), open(LISTA, "w"))
            print(f"--- conta {conta} sem rateio: {tirar_rateio(caminho, {conta})} partida(s) ajustadas; reenviando",
                  flush=True)
        else:
            sys.exit(f"PARADO no lote {lote}: tentativas demais.")
    print("\nFIM: todos os lotes gravados e conferidos.")


if __name__ == "__main__":
    main()

#!/bin/bash
# Balancete do SAP (F.01 / RFBILA00) pelo SAP GUI para HTML, só leitura.
#   baixar_balancete.sh AAAAMM PASTA
# Precisa do SAP acessível (VPN/túnel) e das credenciais em ~/.contabil-sap-gui (ver sap_webgui.mjs).
set -euo pipefail
AQUI=$(cd "$(dirname "$0")" && pwd)
AAAAMM=$1; DESTINO=$2
[[ $AAAAMM =~ ^[0-9]{6}$ ]] || { echo "uso: baixar_balancete.sh AAAAMM PASTA" >&2; exit 1; }
mkdir -p "$DESTINO"
node "$AQUI/sap_webgui.mjs" balancete "$DESTINO" "$AAAAMM"
python3 "$AQUI/lista_para_txt.py" "$DESTINO/lista.json" "$DESTINO/BALANCETE_${AAAAMM:4:2}.${AAAAMM:0:4}.xls"

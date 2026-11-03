"""Conexão RFC com o SAP (somente leitura), via PyRFC.

Configuração por variáveis de ambiente: SAP_ASHOST, SAP_SYSNR, SAP_CLIENT, SAP_USER, SAP_PASSWD (e SAP_LANG,
opcional). Se o SAP só é acessível por VPN, suba a VPN antes de rodar a extração.
"""
import os


class Conexao:
    def __init__(self):
        from pyrfc import Connection  # importado aqui para os outros módulos rodarem sem o SDK do SAP

        self._con = Connection(
            ashost=os.environ["SAP_ASHOST"],
            sysnr=os.environ.get("SAP_SYSNR", "00"),
            client=os.environ["SAP_CLIENT"],
            user=os.environ["SAP_USER"],
            passwd=os.environ["SAP_PASSWD"],
            lang=os.environ.get("SAP_LANG", "PT"),
        )

    def call(self, funcao, **parametros):
        return self._con.call(funcao, **parametros)

    def close(self):
        self._con.close()

"""Atende o botão "Executar agora" do portal (contabil.robo_pedido). Roda no servidor do robô pelo cron a cada minuto.

Pega o pedido mais antigo em 'fila', roda o robo_noturno.py (mesmo fluxo das 22h; com o período escolhido no portal, ou
dia 1 do mês até hoje se o pedido não tiver período) e, no fim,
liga o pedido à execução gravada no portal. Se o robô já estiver rodando (22h ou outro pedido), deixa o pedido na
fila para o minuto seguinte. Pedido 'rodando' sem robô rodando (servidor reiniciou no meio) vira 'erro'.
"""
import fcntl
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(os.path.dirname(AQUI), "app"), AQUI]
import robo_noturno as r  # noqa: E402

LOG = os.path.join(r.SAIDA, "robo.log")


def robo_livre():
    """True se nenhuma execução do robô está rodando (a trava do robo_noturno está solta)."""
    with open(os.path.join(r.SAIDA, ".trava"), "w") as t:
        try:
            fcntl.flock(t, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(t, fcntl.LOCK_UN)
        return True


def main():
    os.makedirs(r.SAIDA, exist_ok=True)
    propria = open(os.path.join(r.SAIDA, ".trava-pedido"), "w")
    try:
        fcntl.flock(propria, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0                                         # outro atendente já está cuidando
    r.garantir_database_url()
    import tabelas
    with tabelas._conectar() as con:
        presos = con.execute("select id from contabil.robo_pedido where sigla = %s and status = 'rodando'",
                             (r.SIGLA,)).fetchall()
        pedido = con.execute("select id, pedido_por, de, ate from contabil.robo_pedido where sigla = %s and status = 'fila' "
                             "order by id limit 1", (r.SIGLA,)).fetchone()
    if presos and robo_livre():
        with tabelas._conectar() as con, con.transaction():
            con.execute("update contabil.robo_pedido set status = 'erro', terminado_em = now(), mensagem = "
                        "'interrompido: o robô parou sem terminar o pedido' where sigla = %s and status = 'rodando'",
                        (r.SIGLA,))
    if not pedido or not robo_livre():
        return 0
    pid, por, de, ate = pedido
    periodo = ["--de", de.isoformat(), "--ate", ate.isoformat()] if de and ate else []
    with tabelas._conectar() as con, con.transaction():
        inicio = con.execute("update contabil.robo_pedido set status = 'rodando', iniciado_em = now() where id = %s "
                             "and status = 'fila' returning iniciado_em", (pid,)).fetchone()
    if not inicio:
        return 0
    with open(LOG, "a") as log:
        log.write(f"--- pedido {pid} do portal ({por}){f' período {de:%d/%m/%Y} a {ate:%d/%m/%Y}' if periodo else ''} ---\n")
        log.flush()
        rc = subprocess.run([sys.executable, os.path.join(AQUI, "robo_noturno.py"), *periodo], stdout=log,
                            stderr=subprocess.STDOUT, cwd=os.path.dirname(AQUI)).returncode
    with tabelas._conectar() as con, con.transaction():
        ex = con.execute("select id, status from contabil.robo_execucao where iniciado_em >= %s - interval '5 seconds' "
                         "order by id limit 1", (inicio[0],)).fetchone()
        if rc == 1 and not ex:                           # o robô das 22h pegou a trava no meio: volta para a fila
            con.execute("update contabil.robo_pedido set status = 'fila', iniciado_em = null where id = %s", (pid,))
            return 0
        if ex:
            con.execute("update contabil.robo_execucao set observacao = concat_ws(' ', nullif(observacao, ''), "
                        "%s::text) where id = %s", (f"Executada pelo botão do portal ({por}).", ex[0]))
        con.execute("update contabil.robo_pedido set status = %s, terminado_em = now(), execucao_id = %s, "
                    "mensagem = %s where id = %s",
                    ("feito" if ex and ex[1] != "erro" else "erro", ex[0] if ex else None,
                     f"execução {ex[0]}: {ex[1]}" if ex else f"o robô saiu com código {rc} sem registrar execução",
                     pid))
    return 0


if __name__ == "__main__":
    sys.exit(main())

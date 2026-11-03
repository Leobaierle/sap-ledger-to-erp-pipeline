"""Arquivos das execuções do robô (Razão extraído do SAP e planilha de importação) no MinIO, bucket
`contabil`, para download pelo portal. O banco guarda só o endereço (`s3://contabil/<chave>`).

Credenciais: variáveis MINIO_ENDPOINT, MINIO_ACCESS_KEY e MINIO_SECRET_KEY ou o arquivo
~/.contabil-minio (mesmas chaves, uma por linha, CHAVE=valor; chmod 600). Nunca impressas."""
import io
import os

BUCKET = "contabil"


def _config():
    c = {k: os.environ.get(k) for k in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY")}
    if not all(c.values()):
        caminho = os.path.expanduser("~/.contabil-minio")
        if os.path.exists(caminho):
            for linha in open(caminho):
                k, _, v = linha.strip().partition("=")
                if k in c and not c[k]:
                    c[k] = v.strip()
    if not all(c.values()):
        raise RuntimeError("MinIO sem credenciais (MINIO_ENDPOINT/MINIO_ACCESS_KEY/MINIO_SECRET_KEY ou ~/.contabil-minio)")
    return c


def configurado():
    try:
        _config()
        return True
    except RuntimeError:
        return False


def _cliente():
    from minio import Minio
    c = _config()
    endereco = c["MINIO_ENDPOINT"].removeprefix("http://").removeprefix("https://").rstrip("/")
    return Minio(endereco, access_key=c["MINIO_ACCESS_KEY"], secret_key=c["MINIO_SECRET_KEY"],
                 secure=c["MINIO_ENDPOINT"].startswith("https://"))


def enviar(caminho, chave):
    """Grava o arquivo local no bucket e devolve o endereço para guardar no banco."""
    _cliente().fput_object(BUCKET, chave, caminho)
    return f"s3://{BUCKET}/{chave}"


def ler(endereco):
    """Devolve (nome do arquivo, conteúdo em BytesIO) de um endereço s3://contabil/<chave>."""
    bucket, _, chave = endereco.removeprefix("s3://").partition("/")
    r = _cliente().get_object(bucket, chave)
    try:
        return os.path.basename(chave), io.BytesIO(r.read())
    finally:
        r.close()
        r.release_conn()

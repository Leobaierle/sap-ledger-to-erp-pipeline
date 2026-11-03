-- 19/10/2026: balancete do SAP (FAGLFLEXT), extraído junto com o Razão, para download no portal.
-- Os arquivos (Razão, balancete, planilha) ficam no MinIO, bucket contabil; a coluna guarda s3://contabil/<chave>.
alter table contabil.robo_execucao add column if not exists arquivo_balancete text;

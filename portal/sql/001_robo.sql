-- Estado do robô diário (SAP -> conversão -> ERP) lido e escrito pelo portal. Roda como contabil_app.
-- As tabelas de de-para (plano_contas, centro_custo, contas_sap, historico) são as do conversor (000_schema.sql).

create table if not exists contabil.robo_config (
  chave text primary key,
  valor jsonb not null,
  atualizado_em timestamptz not null default now()
);
insert into contabil.robo_config (chave, valor) values
  ('ambiente', '"EMP"'),          -- sigla de destino na ERP: só EMP (15/10/2026: sem empresa de teste)
  ('horario', 'null')             -- horário da execução noturna; null = a definir
on conflict (chave) do nothing;

-- uma linha por noite (ou execução manual)
create table if not exists contabil.robo_execucao (
  id bigint generated always as identity primary key,
  data date not null,                       -- dia da execução
  sigla text not null,                      -- TST / EMP
  status text not null,                     -- agendado, andamento, sucesso, pendencias, erro, verificar, sem
  periodo_de date,
  periodo_ate date,
  iniciado_em timestamptz,
  terminado_em timestamptz,
  docs_extraidos int not null default 0,    -- documentos no período no SAP
  docs_novos int not null default 0,        -- importados nesta execução
  docs_segurados int not null default 0,
  lancamentos int not null default 0,
  linhas int not null default 0,
  partes int not null default 0,
  debito numeric(18,2) not null default 0,
  credito numeric(18,2) not null default 0,
  lote int,
  avisos jsonb not null default '[]',       -- avisos da conversão (texto)
  conferencia text,                         -- status verificar: 'gravou' | 'nao' (registrado no portal)
  conferencia_em timestamptz,
  arquivo_planilha text,                    -- caminho do arquivo gerado (download pelo portal)
  arquivo_razao text,
  observacao text not null default ''
);
create index if not exists robo_execucao_data on contabil.robo_execucao (data desc);

create table if not exists contabil.robo_etapa (
  execucao_id bigint not null references contabil.robo_execucao(id) on delete cascade,
  n smallint not null,                      -- 1 Extração SAP, 2 Conversão, 3 Envio p/ ERP, 4 Importação ERP
  status text not null,                     -- + naoexec
  iniciado_em timestamptz,
  terminado_em timestamptz,
  nota text not null default '',
  primary key (execucao_id, n)
);

create table if not exists contabil.robo_log (
  id bigint generated always as identity primary key,
  execucao_id bigint not null references contabil.robo_execucao(id) on delete cascade,
  quando timestamptz not null default now(),
  nivel text not null,                      -- info, aviso, erro
  etapa text not null,
  mensagem text not null
);
create index if not exists robo_log_execucao on contabil.robo_log (execucao_id, quando, id);

create table if not exists contabil.robo_print (
  id bigint generated always as identity primary key,
  execucao_id bigint not null references contabil.robo_execucao(id) on delete cascade,
  quando timestamptz not null,
  arquivo text not null,
  legenda text not null default ''
);

-- documentos do SAP já gravados na ERP (fonte da verdade do "já importado"), por sigla
create table if not exists contabil.robo_documento (
  sigla text not null,
  doc text not null,                        -- Nº doc. SAP (BELNR, sem zeros à esquerda)
  ano smallint not null,                    -- GJAHR
  data_lancamento date not null,
  lote int not null,
  execucao_id bigint references contabil.robo_execucao(id),
  importado_em timestamptz not null default now(),
  referencia text not null default '',      -- para detectar alteração no SAP depois de importado
  textos jsonb not null default '[]',
  primary key (sigla, doc, ano)
);

-- documentos segurados por conta SAP sem conta ERP
create table if not exists contabil.robo_segurado (
  sigla text not null,
  doc text not null,
  ano smallint not null,
  data_lancamento date not null,
  valor numeric(18,2) not null,             -- soma dos débitos do documento
  contas_sap text[] not null,               -- contas que faltam
  desde date not null,
  liberado_em timestamptz,                  -- importado depois de preenchida a conta
  primary key (sigla, doc, ano)
);

-- pendências encontradas na última conversão (o robô regrava a cada noite)
create table if not exists contabil.robo_pendencia (
  sigla text not null,
  tipo text not null,                       -- conta | cc
  codigo_sap text not null,
  nome_sap text not null default '',
  docs int not null default 0,
  linhas int not null default 0,
  debito numeric(18,2) not null default 0,
  credito numeric(18,2) not null default 0,
  valor numeric(18,2) not null default 0,
  conta_exemplo text not null default '',
  historico_exemplo text not null default '',
  execucao_id bigint references contabil.robo_execucao(id) on delete set null,
  atualizado_em timestamptz not null default now(),
  primary key (sigla, tipo, codigo_sap)
);

-- documentos que mudaram no SAP depois de importados (informativo)
create table if not exists contabil.robo_alteracao (
  id bigint generated always as identity primary key,
  sigla text not null,
  doc text not null,
  data_lancamento date not null,
  lote int not null,
  campo text not null,                      -- Texto | Referência
  antes text not null,
  depois text not null,
  detectado_em date not null default current_date
);

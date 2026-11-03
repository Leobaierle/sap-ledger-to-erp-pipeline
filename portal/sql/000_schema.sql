-- Schema do conversor contábil (Razão SAP -> importação ERP). Roda como contabil_app.
create table if not exists contabil.plano_contas (
  id bigint generated always as identity primary key,
  conta_sap text not null,            -- não é única de propósito: a planilha tem conta SAP duplicada (o site aponta)
  conta_erp text not null,
  nome_conta text not null default '',
  sintetica_erp text not null default '',
  conta_referencial text not null default '',
  atualizado_em timestamptz not null default now()
);
create index if not exists plano_contas_conta_sap on contabil.plano_contas (conta_sap);

create table if not exists contabil.centro_custo (
  centro_custo_sap text primary key,
  centro_custo_resumido text not null default '',
  centro_custo_erp text not null,
  atualizado_em timestamptz not null default now()
);

create table if not exists contabil.contas_sap (
  conta_sap text primary key,
  nome_conta_sap text not null default ''
);

-- trilha de toda mudança feita pelo site nas tabelas acima
create table if not exists contabil.historico (
  id bigint generated always as identity primary key,
  quando timestamptz not null default now(),
  tabela text not null,
  origem text not null,
  dados jsonb not null
);

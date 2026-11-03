-- 15/10/2026: importação avulsa — ao preencher a conta/CC no portal, os documentos liberados entram numa fila e um
-- CronJob no k3s (sap/importar_fila.py) grava na ERP pela ERP API, sem esperar a próxima importação.

-- linhas do Razão SAP do documento segurado (para converter de novo sem voltar ao SAP)
alter table contabil.robo_segurado add column if not exists linhas jsonb not null default '[]';

-- contas ERP que recusam rateio de centro de custo (a API recusa o lote inteiro se vier rateio nelas)
create table if not exists contabil.robo_conta_sem_rateio (
  sigla text not null,
  conta int not null,
  desde timestamptz not null default now(),
  primary key (sigla, conta)
);

create table if not exists contabil.robo_fila (
  id bigint generated always as identity primary key,
  sigla text not null,
  criado_em timestamptz not null default now(),
  origem text not null default '',          -- portal:<e-mail>
  motivo text not null default '',          -- ex.: "CC 120212050 → 1234"
  docs text[] not null,
  status text not null default 'fila' check (status in ('fila', 'gravando', 'importado', 'vazio', 'erro')),
  iniciado_em timestamptz,
  terminado_em timestamptz,
  lotes int[] not null default '{}',
  partidas int not null default 0,
  debito numeric(18,2) not null default 0,
  mensagem text not null default ''
);
create index if not exists robo_fila_status on contabil.robo_fila (sigla, status, id);

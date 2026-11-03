-- 15/10/2026: documento com centro de custo SAP sem de-para também fica segurado até o de-para ser preenchido
alter table contabil.robo_segurado add column if not exists ccs_sap text[] not null default '{}';

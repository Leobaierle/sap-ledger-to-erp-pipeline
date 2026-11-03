-- 21/10/2026: botão "Executar agora" do portal. O portal só grava o pedido; o servidor do robô (sap/atender_pedido.py, cron
-- a cada minuto) pega o pedido, roda o robô (mesmo fluxo das 22h: dia 1 até agora) e liga o pedido à execução.
create table if not exists contabil.robo_pedido (
  id bigint generated always as identity primary key,
  sigla text not null,
  pedido_por text not null default '',      -- e-mail de quem clicou
  criado_em timestamptz not null default now(),
  status text not null default 'fila' check (status in ('fila', 'rodando', 'feito', 'erro')),
  iniciado_em timestamptz,
  terminado_em timestamptz,
  execucao_id bigint references contabil.robo_execucao (id),
  mensagem text not null default ''
);
-- no máximo um pedido aberto por empresa (clique duplo não vira duas execuções)
create unique index if not exists robo_pedido_aberto on contabil.robo_pedido (sigla) where status in ('fila', 'rodando');

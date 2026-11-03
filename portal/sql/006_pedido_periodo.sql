-- 03/11/2026: o botão "Executar agora" pergunta a competência e o período (de/até, dentro do mês, até hoje).
-- Pedido sem período (antigos) = dia 1 do mês até hoje, como antes.
alter table contabil.robo_pedido add column if not exists de date;
alter table contabil.robo_pedido add column if not exists ate date;

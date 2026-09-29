-- INTRODUÇÃO
-- Migração 003: camada semântica (`analytics`). Cada métrica é definida UMA ÚNICA
-- VEZ aqui, em views, e documentada na tabela `catalogo_metricas` (nome, descrição,
-- fórmula e fonte). O Dashboard e o agente de IA consultam as mesmas views, o que
-- garante que os dois nunca mostrem números diferentes para a mesma pergunta.
-- Convenções:
--   * competencia: texto 'AAAA-MM' (igual a metas_mensais);
--   * VGV (Valor Geral de Vendas): soma de valor_negocio apenas de VENDAS fechadas;
--     para locação, valor_negocio = 12 x aluguel (valor anual do contrato);
--   * ticket médio: média de valor_negocio das vendas fechadas;
--   * taxa de conversão lead->negócio: fechados / leads no mesmo recorte;
--   * tempo médio de fechamento: média de (data_fechamento - data_abertura) dos
--     negócios fechados, em dias.
-- Os grãos incluem as dimensões de filtro do Dashboard (cidade, finalidade, tipo,
-- origem, equipe/corretor) para que período + filtros funcionem em qualquer view.
-- RESUMO: views de métricas (funil, VGV, conversão, ranking, perdas, metas) +
-- tabela de catálogo que documenta cada métrica para humanos e para o agente.

-- ---------------------------------------------------------------------------
-- View granular de negócios: base para várias métricas e para o agente.
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.v_negocios_detalhe AS
SELECT
    n.negocio_id,
    n.data_abertura,
    n.data_fechamento,
    to_char(n.data_fechamento, 'YYYY-MM') AS competencia,
    n.status,
    n.finalidade,
    i.tipo,
    b.bairro,
    b.bairro_id,
    c.cidade,
    c.cidade_id,
    co.corretor_id,
    co.nome_corretor AS corretor,
    e.equipe_id,
    e.nome_equipe AS equipe,
    o.origem_id,
    o.nome_origem AS origem,
    n.valor_negocio,
    n.perc_comissao,
    n.valor_comissao,
    (n.data_fechamento - n.data_abertura) AS tempo_fechamento_dias,
    n.motivo_perda
FROM curated.fato_negocios n
JOIN curated.imoveis      i  ON i.imovel_id   = n.imovel_id
JOIN curated.dim_bairro   b  ON b.bairro_id   = i.bairro_id
JOIN curated.dim_cidade   c  ON c.cidade_id   = b.cidade_id
JOIN curated.dim_corretor co ON co.corretor_id = n.corretor_id
JOIN curated.dim_equipe   e  ON e.equipe_id   = co.equipe_id
JOIN curated.fato_leads   l  ON l.lead_id     = n.lead_id
JOIN curated.dim_origem   o  ON o.origem_id   = l.origem_id
WHERE n.data_fechamento IS NOT NULL;
COMMENT ON VIEW analytics.v_negocios_detalhe IS 'Uma linha por negócio (fechado ou perdido) com todas as dimensões: base de VGV, comissões, ticket médio, tempo de fechamento e motivos de perda.';

-- ---------------------------------------------------------------------------
-- Funil mensal: cada etapa entra no mês da sua própria data
-- (lead pela data do lead, visita pela data da visita, etc.).
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.v_funil_mensal AS
WITH estagios AS (
    SELECT to_char(l.data, 'YYYY-MM') AS competencia,
           l.origem_id, l.cidade_id, l.finalidade, l.tipo_procurado AS tipo,
           co.equipe_id, l.corretor_id,
           1 AS leads, 0 AS visitas, 0 AS propostas, 0 AS fechados, 0 AS perdidos
    FROM curated.fato_leads l
    JOIN curated.dim_corretor co ON co.corretor_id = l.corretor_id
    UNION ALL
    SELECT to_char(v.data, 'YYYY-MM'),
           l.origem_id, l.cidade_id, l.finalidade, i.tipo, co.equipe_id, v.corretor_id,
           0, CASE WHEN v.compareceu THEN 1 ELSE 0 END, 0, 0, 0
    FROM curated.fato_visitas v
    JOIN curated.fato_leads   l  ON l.lead_id = v.lead_id
    JOIN curated.imoveis      i  ON i.imovel_id = v.imovel_id
    JOIN curated.dim_corretor co ON co.corretor_id = v.corretor_id
    UNION ALL
    SELECT to_char(p.data, 'YYYY-MM'),
           l.origem_id, l.cidade_id, l.finalidade, i.tipo, co.equipe_id, l.corretor_id,
           0, 0, 1, 0, 0
    FROM curated.fato_propostas p
    JOIN curated.fato_leads   l  ON l.lead_id = p.lead_id
    JOIN curated.imoveis      i  ON i.imovel_id = p.imovel_id
    JOIN curated.dim_corretor co ON co.corretor_id = l.corretor_id
    UNION ALL
    SELECT to_char(n.data_fechamento, 'YYYY-MM'),
           l.origem_id, l.cidade_id, n.finalidade, i.tipo, co.equipe_id, n.corretor_id,
           0, 0, 0,
           CASE WHEN n.status = 'fechado' THEN 1 ELSE 0 END,
           CASE WHEN n.status = 'perdido' THEN 1 ELSE 0 END
    FROM curated.fato_negocios n
    JOIN curated.fato_leads   l  ON l.lead_id = n.lead_id
    JOIN curated.imoveis      i  ON i.imovel_id = n.imovel_id
    JOIN curated.dim_corretor co ON co.corretor_id = n.corretor_id
    WHERE n.data_fechamento IS NOT NULL
)
SELECT competencia, origem_id, cidade_id, finalidade, tipo, equipe_id, corretor_id,
       SUM(leads)     AS leads,
       SUM(visitas)   AS visitas,
       SUM(propostas) AS propostas,
       SUM(fechados)  AS fechados,
       SUM(perdidos)  AS perdidos
FROM estagios
GROUP BY competencia, origem_id, cidade_id, finalidade, tipo, equipe_id, corretor_id;
COMMENT ON VIEW analytics.v_funil_mensal IS 'Funil comercial por mês e dimensões: leads, visitas (comparecidas), propostas, negócios fechados e perdidos. Cada etapa conta no mês da sua própria data.';

-- ---------------------------------------------------------------------------
-- VGV, negócios e comissões por mês e finalidade.
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.v_vgv_mensal AS
SELECT to_char(n.data_fechamento, 'YYYY-MM') AS competencia,
       n.finalidade,
       i.tipo,
       b.cidade_id,
       co.equipe_id,
       n.corretor_id,
       COUNT(*)              AS negocios_fechados,
       SUM(n.valor_negocio)  AS vgv,
       SUM(n.valor_comissao) AS comissao_total,
       AVG(n.valor_negocio)  AS ticket_medio,
       AVG(n.data_fechamento - n.data_abertura) AS tempo_medio_fechamento_dias
FROM curated.fato_negocios n
JOIN curated.imoveis      i  ON i.imovel_id = n.imovel_id
JOIN curated.dim_bairro   b  ON b.bairro_id = i.bairro_id
JOIN curated.dim_corretor co ON co.corretor_id = n.corretor_id
WHERE n.status = 'fechado' AND n.data_fechamento IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, 6;
COMMENT ON VIEW analytics.v_vgv_mensal IS 'Negócios fechados por mês/finalidade/tipo/cidade/equipe/corretor: quantidade, VGV, comissões, ticket médio e tempo médio de fechamento (dias).';

-- ---------------------------------------------------------------------------
-- Conversão por origem do lead (leads pelo mês de entrada; fechados pelo mês
-- de fechamento, com a origem do lead que o originou).
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.v_conversao_origem AS
WITH leads AS (
    SELECT to_char(l.data, 'YYYY-MM') AS competencia, l.origem_id, COUNT(*) AS leads
    FROM curated.fato_leads l
    GROUP BY 1, 2
), fechados AS (
    SELECT to_char(n.data_fechamento, 'YYYY-MM') AS competencia, l.origem_id, COUNT(*) AS fechados
    FROM curated.fato_negocios n
    JOIN curated.fato_leads l ON l.lead_id = n.lead_id
    WHERE n.status = 'fechado' AND n.data_fechamento IS NOT NULL
    GROUP BY 1, 2
)
SELECT l.competencia,
       l.origem_id,
       o.nome_origem AS origem,
       l.leads,
       COALESCE(f.fechados, 0) AS fechados,
       ROUND(COALESCE(f.fechados, 0)::NUMERIC / NULLIF(l.leads, 0), 4) AS taxa_conversao
FROM leads l
JOIN curated.dim_origem o ON o.origem_id = l.origem_id
LEFT JOIN fechados f ON f.competencia = l.competencia AND f.origem_id = l.origem_id;
COMMENT ON VIEW analytics.v_conversao_origem IS 'Leads e negócios fechados por mês e origem, com taxa de conversão (fechados/leads).';

-- ---------------------------------------------------------------------------
-- Ranking de corretores por mês.
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.v_ranking_corretores AS
SELECT to_char(n.data_fechamento, 'YYYY-MM') AS competencia,
       co.corretor_id,
       co.nome_corretor AS corretor,
       e.equipe_id,
       e.nome_equipe AS equipe,
       COUNT(*) AS negocios_fechados,
       SUM(n.valor_negocio) FILTER (WHERE n.finalidade = 'venda') AS vgv_vendas,
       SUM(n.valor_comissao) AS comissao_total,
       AVG(n.valor_negocio) FILTER (WHERE n.finalidade = 'venda') AS ticket_medio_vendas
FROM curated.fato_negocios n
JOIN curated.dim_corretor co ON co.corretor_id = n.corretor_id
JOIN curated.dim_equipe   e  ON e.equipe_id = co.equipe_id
WHERE n.status = 'fechado' AND n.data_fechamento IS NOT NULL
GROUP BY 1, 2, 3, 4, 5;
COMMENT ON VIEW analytics.v_ranking_corretores IS 'Desempenho mensal por corretor: negócios fechados, VGV de vendas, comissões e ticket médio.';

-- ---------------------------------------------------------------------------
-- Motivos de perda por mês (para gráfico de Pareto).
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.v_motivos_perda AS
SELECT to_char(n.data_fechamento, 'YYYY-MM') AS competencia,
       n.motivo_perda,
       COUNT(*) AS total
FROM curated.fato_negocios n
WHERE n.status = 'perdido' AND n.motivo_perda IS NOT NULL
GROUP BY 1, 2;
COMMENT ON VIEW analytics.v_motivos_perda IS 'Quantidade de negócios perdidos por mês e motivo de perda.';

-- ---------------------------------------------------------------------------
-- Negócios fechados por bairro e tipo de imóvel (por mês).
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.v_negocios_bairro_tipo AS
SELECT to_char(n.data_fechamento, 'YYYY-MM') AS competencia,
       c.cidade_id,
       c.cidade,
       b.bairro_id,
       b.bairro,
       i.tipo,
       n.finalidade,
       COUNT(*)             AS negocios_fechados,
       SUM(n.valor_negocio) AS vgv
FROM curated.fato_negocios n
JOIN curated.imoveis    i ON i.imovel_id = n.imovel_id
JOIN curated.dim_bairro b ON b.bairro_id = i.bairro_id
JOIN curated.dim_cidade c ON c.cidade_id = b.cidade_id
WHERE n.status = 'fechado' AND n.data_fechamento IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, 6, 7;
COMMENT ON VIEW analytics.v_negocios_bairro_tipo IS 'Negócios fechados e VGV por mês, cidade, bairro, tipo de imóvel e finalidade.';

-- ---------------------------------------------------------------------------
-- Realizado x meta por equipe e mês.
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.v_realizado_meta AS
SELECT m.competencia,
       m.equipe_id,
       e.nome_equipe AS equipe,
       COUNT(n.negocio_id) FILTER (WHERE n.status = 'fechado') AS realizado_negocios,
       COALESCE(SUM(n.valor_negocio) FILTER (WHERE n.status = 'fechado' AND n.finalidade = 'venda'), 0) AS realizado_vgv,
       m.meta_negocios,
       m.meta_vgv,
       ROUND(COUNT(n.negocio_id) FILTER (WHERE n.status = 'fechado')::NUMERIC / NULLIF(m.meta_negocios, 0), 4) AS perc_atingido_negocios,
       ROUND(COALESCE(SUM(n.valor_negocio) FILTER (WHERE n.status = 'fechado' AND n.finalidade = 'venda'), 0) / NULLIF(m.meta_vgv, 0), 4) AS perc_atingido_vgv
FROM curated.metas_mensais m
JOIN curated.dim_equipe e ON e.equipe_id = m.equipe_id
LEFT JOIN curated.dim_corretor co ON co.equipe_id = m.equipe_id
LEFT JOIN curated.fato_negocios n
       ON n.corretor_id = co.corretor_id
      AND to_char(n.data_fechamento, 'YYYY-MM') = m.competencia
      AND n.data_fechamento IS NOT NULL
WHERE m.corretor_id IS NULL  -- meta da equipe inteira
GROUP BY m.competencia, m.equipe_id, e.nome_equipe, m.meta_negocios, m.meta_vgv;
COMMENT ON VIEW analytics.v_realizado_meta IS 'Realizado x meta mensal por equipe: negócios e VGV realizados contra as metas, com percentual de atingimento.';

-- ---------------------------------------------------------------------------
-- Catálogo de métricas: documentação oficial consumida pelo agente de IA
-- (ferramenta `listar_metricas_e_dimensoes`) e reproduzida no README.
-- ---------------------------------------------------------------------------
CREATE TABLE analytics.catalogo_metricas (
    metrica    TEXT PRIMARY KEY,
    nome       TEXT NOT NULL,
    descricao  TEXT NOT NULL,
    formula    TEXT NOT NULL,
    fonte      TEXT NOT NULL,
    unidade    TEXT NOT NULL
);
COMMENT ON TABLE  analytics.catalogo_metricas IS 'Catálogo semântico: definição única de cada métrica (nome, descrição, fórmula, fonte, unidade).';
COMMENT ON COLUMN analytics.catalogo_metricas.metrica   IS 'Identificador da métrica usado pela ferramenta consultar_metrica.';
COMMENT ON COLUMN analytics.catalogo_metricas.nome      IS 'Nome de exibição.';
COMMENT ON COLUMN analytics.catalogo_metricas.descricao IS 'O que a métrica mede.';
COMMENT ON COLUMN analytics.catalogo_metricas.formula   IS 'Fórmula/regra de cálculo.';
COMMENT ON COLUMN analytics.catalogo_metricas.fonte     IS 'View do schema analytics que fornece o dado.';
COMMENT ON COLUMN analytics.catalogo_metricas.unidade   IS 'Unidade: quantidade, reais, percentual ou dias.';

INSERT INTO analytics.catalogo_metricas (metrica, nome, descricao, formula, fonte, unidade) VALUES
('leads_recebidos',          'Leads recebidos',            'Total de leads que entraram no funil.', 'SUM(leads)', 'analytics.v_funil_mensal', 'quantidade'),
('visitas_realizadas',       'Visitas realizadas',         'Visitas em que o cliente compareceu.', 'SUM(visitas) com compareceu = true', 'analytics.v_funil_mensal', 'quantidade'),
('propostas_enviadas',       'Propostas enviadas',         'Propostas enviadas a clientes.', 'SUM(propostas)', 'analytics.v_funil_mensal', 'quantidade'),
('negocios_fechados',        'Negócios fechados',          'Negócios com status fechado (venda ou locação).', 'SUM(fechados)', 'analytics.v_funil_mensal', 'quantidade'),
('vgv',                      'VGV (Valor Geral de Vendas)','Soma do valor dos negócios de VENDA fechados.', 'SUM(valor_negocio) WHERE finalidade = venda AND status = fechado', 'analytics.v_vgv_mensal', 'reais'),
('receita_comissoes',        'Receita de comissões',       'Soma das comissões dos negócios fechados.', 'SUM(valor_comissao) WHERE status = fechado', 'analytics.v_vgv_mensal', 'reais'),
('ticket_medio',             'Ticket médio',               'Valor médio dos negócios de VENDA fechados.', 'AVG(valor_negocio) WHERE finalidade = venda AND status = fechado', 'analytics.v_vgv_mensal', 'reais'),
('taxa_conversao',           'Taxa de conversão',          'Negócios fechados dividido pelos leads recebidos no mesmo recorte.', 'SUM(fechados) / SUM(leads)', 'analytics.v_funil_mensal', 'percentual'),
('tempo_medio_fechamento',   'Tempo médio de fechamento',  'Média de dias entre abertura e fechamento dos negócios fechados.', 'AVG(data_fechamento - data_abertura) WHERE status = fechado', 'analytics.v_vgv_mensal', 'dias'),
('funil',                    'Funil comercial',            'Leads, visitas, propostas, fechados e perdidos por etapa.', 'SUM por etapa', 'analytics.v_funil_mensal', 'quantidade'),
('conversao_por_origem',     'Conversão por origem',       'Leads, fechados e taxa de conversão por origem do lead.', 'fechados / leads por origem', 'analytics.v_conversao_origem', 'percentual'),
('ranking_corretores',       'Ranking de corretores',      'Negócios, VGV e comissões por corretor.', 'agregação por corretor', 'analytics.v_ranking_corretores', 'quantidade'),
('motivos_perda',            'Motivos de perda',           'Negócios perdidos por motivo.', 'COUNT por motivo_perda WHERE status = perdido', 'analytics.v_motivos_perda', 'quantidade'),
('negocios_por_bairro_tipo', 'Negócios por bairro e tipo', 'Negócios fechados e VGV por bairro e tipo de imóvel.', 'agregação por bairro/tipo', 'analytics.v_negocios_bairro_tipo', 'quantidade'),
('realizado_vs_meta',        'Realizado x meta',           'Realizado contra meta mensal por equipe.', 'realizado / meta', 'analytics.v_realizado_meta', 'percentual');

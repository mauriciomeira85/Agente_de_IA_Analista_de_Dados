-- INTRODUÇÃO
-- Corrige filtros ignorados e datas arredondadas. As views preservam seus nomes
-- públicos e agora carregam data_ref e todas as dimensões do dashboard.
BEGIN;
CREATE OR REPLACE VIEW analytics.v_funil_mensal AS
WITH estagios AS (
    SELECT l.data AS data_ref, to_char(l.data, 'YYYY-MM') AS competencia,
           l.origem_id, l.cidade_id, l.finalidade, l.tipo_procurado AS tipo,
           co.equipe_id, l.corretor_id,
           1 AS leads, 0 AS visitas, 0 AS propostas, 0 AS fechados, 0 AS perdidos
    FROM curated.fato_leads l
    JOIN curated.dim_corretor co ON co.corretor_id = l.corretor_id
    UNION ALL
    SELECT v.data, to_char(v.data, 'YYYY-MM'),
           l.origem_id, l.cidade_id, l.finalidade, i.tipo, co.equipe_id, v.corretor_id,
           0, CASE WHEN v.compareceu THEN 1 ELSE 0 END, 0, 0, 0
    FROM curated.fato_visitas v
    JOIN curated.fato_leads   l  ON l.lead_id = v.lead_id
    JOIN curated.imoveis      i  ON i.imovel_id = v.imovel_id
    JOIN curated.dim_corretor co ON co.corretor_id = v.corretor_id
    UNION ALL
    SELECT p.data, to_char(p.data, 'YYYY-MM'),
           l.origem_id, l.cidade_id, l.finalidade, i.tipo, co.equipe_id, l.corretor_id,
           0, 0, 1, 0, 0
    FROM curated.fato_propostas p
    JOIN curated.fato_leads   l  ON l.lead_id = p.lead_id
    JOIN curated.imoveis      i  ON i.imovel_id = p.imovel_id
    JOIN curated.dim_corretor co ON co.corretor_id = l.corretor_id
    UNION ALL
    SELECT n.data_fechamento, to_char(n.data_fechamento, 'YYYY-MM'),
           l.origem_id, b.cidade_id, n.finalidade, i.tipo, co.equipe_id, n.corretor_id,
           0, 0, 0,
           CASE WHEN n.status = 'fechado' THEN 1 ELSE 0 END,
           CASE WHEN n.status = 'perdido' THEN 1 ELSE 0 END
    FROM curated.fato_negocios n
    JOIN curated.fato_leads   l  ON l.lead_id = n.lead_id
    JOIN curated.imoveis      i  ON i.imovel_id = n.imovel_id
    JOIN curated.dim_bairro b ON b.bairro_id = i.bairro_id
    JOIN curated.dim_corretor co ON co.corretor_id = n.corretor_id
    WHERE n.data_fechamento IS NOT NULL
)
SELECT competencia, origem_id, cidade_id, finalidade, tipo, equipe_id, corretor_id,
       SUM(leads)     AS leads,
       SUM(visitas)   AS visitas,
       SUM(propostas) AS propostas,
       SUM(fechados)  AS fechados,
       SUM(perdidos)  AS perdidos, data_ref
FROM estagios
GROUP BY competencia, origem_id, cidade_id, finalidade, tipo, equipe_id, corretor_id, data_ref;

CREATE OR REPLACE VIEW analytics.v_vgv_mensal AS
SELECT competencia, finalidade, tipo, cidade_id, equipe_id, corretor_id,
       COUNT(*) AS negocios_fechados,
       SUM(valor_negocio) AS vgv, SUM(valor_comissao) AS comissao_total,
       AVG(valor_negocio) AS ticket_medio,
       AVG(tempo_fechamento_dias) AS tempo_medio_fechamento_dias,
       data_fechamento AS data_ref, origem_id, bairro_id
FROM analytics.v_negocios_detalhe WHERE status = 'fechado'
GROUP BY competencia, finalidade, tipo, cidade_id, equipe_id, corretor_id,
         data_fechamento, origem_id, bairro_id;
CREATE OR REPLACE VIEW analytics.v_conversao_origem AS
SELECT f.competencia, f.origem_id, o.nome_origem AS origem,
       f.leads, f.fechados,
       ROUND(f.fechados::numeric / NULLIF(f.leads, 0), 4) AS taxa_conversao,
       f.data_ref, f.cidade_id, f.finalidade, f.tipo, f.equipe_id, f.corretor_id
FROM analytics.v_funil_mensal f JOIN curated.dim_origem o USING (origem_id);
CREATE OR REPLACE VIEW analytics.v_ranking_corretores AS
SELECT competencia, corretor_id, corretor, equipe_id, equipe,
       COUNT(*) AS negocios_fechados,
       SUM(valor_negocio) FILTER (WHERE finalidade = 'venda') AS vgv_vendas,
       SUM(valor_comissao) AS comissao_total,
       AVG(valor_negocio) FILTER (WHERE finalidade = 'venda') AS ticket_medio_vendas,
       data_fechamento AS data_ref, cidade_id, finalidade, tipo, origem_id, bairro_id
FROM analytics.v_negocios_detalhe WHERE status = 'fechado'
GROUP BY competencia, corretor_id, corretor, equipe_id, equipe,
         data_fechamento, cidade_id, finalidade, tipo, origem_id, bairro_id;
CREATE OR REPLACE VIEW analytics.v_motivos_perda AS
SELECT competencia, motivo_perda, COUNT(*) AS total,
       data_fechamento AS data_ref, cidade_id, finalidade, tipo, origem_id, equipe_id, corretor_id, bairro_id
FROM analytics.v_negocios_detalhe WHERE status = 'perdido'
GROUP BY competencia, motivo_perda, data_fechamento, cidade_id, finalidade, tipo, origem_id, equipe_id, corretor_id, bairro_id;
CREATE OR REPLACE VIEW analytics.v_negocios_bairro_tipo AS
SELECT competencia, cidade_id, cidade, bairro_id, bairro, tipo, finalidade,
       COUNT(*) AS negocios_fechados,
       COALESCE(SUM(valor_negocio) FILTER (WHERE finalidade = 'venda'), 0) AS vgv,
       data_fechamento AS data_ref, origem_id, equipe_id, corretor_id
FROM analytics.v_negocios_detalhe WHERE status = 'fechado'
GROUP BY competencia, cidade_id, cidade, bairro_id, bairro, tipo, finalidade,
         data_fechamento, origem_id, equipe_id, corretor_id;
ALTER TABLE app.agente_mensagens ADD COLUMN IF NOT EXISTS artefatos jsonb NOT NULL DEFAULT '[]';
COMMENT ON COLUMN app.agente_mensagens.artefatos IS 'Gráficos e links de arquivos da resposta, preservados ao reabrir o chat.';

-- Dicionário das colunas das views: o mesmo nome de coluna tem o mesmo
-- significado em todas as views de analytics (definição única).
DO $$
DECLARE
    c record;
    descricoes CONSTANT jsonb := '{
      "competencia": "Mês de referência no formato AAAA-MM.",
      "data_ref": "Data exata do evento (lead, visita, proposta ou fechamento); usada nos filtros de período.",
      "negocio_id": "Identificador do negócio.",
      "data_abertura": "Data de abertura do negócio.",
      "data_fechamento": "Data de fechamento (ou de perda) do negócio.",
      "status": "Situação do negócio: fechado ou perdido.",
      "finalidade": "Finalidade: venda ou locacao.",
      "tipo": "Tipo de imóvel: apartamento, casa, sala_comercial ou terreno.",
      "cidade_id": "Identificador da cidade.", "cidade": "Nome da cidade.",
      "bairro_id": "Identificador do bairro.", "bairro": "Nome do bairro.",
      "origem_id": "Identificador da origem do lead.", "origem": "Nome da origem do lead.",
      "equipe_id": "Identificador da equipe.", "equipe": "Nome da equipe.",
      "corretor_id": "Identificador do corretor.", "corretor": "Nome (fictício) do corretor.",
      "leads": "Quantidade de leads recebidos.",
      "visitas": "Quantidade de visitas com comparecimento.",
      "propostas": "Quantidade de propostas enviadas.",
      "fechados": "Quantidade de negócios fechados.",
      "perdidos": "Quantidade de negócios perdidos.",
      "negocios_fechados": "Quantidade de negócios fechados.",
      "valor_negocio": "Valor do negócio em reais (locação: 12 x aluguel).",
      "perc_comissao": "Percentual de comissão do negócio.",
      "valor_comissao": "Valor da comissão em reais.",
      "tempo_fechamento_dias": "Dias entre abertura e fechamento do negócio.",
      "motivo_perda": "Motivo da perda do negócio.",
      "vgv": "VGV em reais: soma do valor das VENDAS fechadas.",
      "vgv_vendas": "VGV em reais: soma do valor das VENDAS fechadas.",
      "comissao_total": "Soma das comissões em reais.",
      "ticket_medio": "Valor médio dos negócios fechados, em reais.",
      "ticket_medio_vendas": "Valor médio das vendas fechadas, em reais.",
      "tempo_medio_fechamento_dias": "Média de dias entre abertura e fechamento.",
      "taxa_conversao": "Negócios fechados / leads (0 a 1).",
      "total": "Quantidade de negócios perdidos.",
      "realizado_negocios": "Negócios fechados no mês pela equipe.",
      "realizado_vgv": "VGV de vendas realizado no mês pela equipe, em reais.",
      "meta_negocios": "Meta de negócios do mês.",
      "meta_vgv": "Meta de VGV do mês, em reais.",
      "perc_atingido_negocios": "Realizado / meta de negócios (0 a 1).",
      "perc_atingido_vgv": "Realizado / meta de VGV (0 a 1)."
    }';
BEGIN
    FOR c IN SELECT table_name, column_name FROM information_schema.columns
             WHERE table_schema = 'analytics' AND table_name LIKE 'v\_%'
    LOOP
        IF descricoes ? c.column_name THEN
            EXECUTE format('COMMENT ON COLUMN analytics.%I.%I IS %L',
                           c.table_name, c.column_name, descricoes ->> c.column_name);
        END IF;
    END LOOP;
END $$;
COMMIT;
-- RESUMO: datas exatas (data_ref), dimensões completas em todas as views,
-- VGV apenas de vendas, artefatos do chat persistidos e dicionário das views.

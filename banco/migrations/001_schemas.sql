-- INTRODUÇÃO
-- Migração 001: cria os schemas do projeto.
--   staging  -> área de trabalho do gerador de dados (recriada a cada carga);
--   curated  -> dados finais (modelo estrela simplificado da imobiliária);
--   analytics-> camada semântica: views com métricas definidas uma única vez;
--   app      -> conversas e mensagens do agente de IA;
--   audit    -> registro de cargas e de execuções do agente (rastreabilidade).
-- RESUMO: cria os 5 schemas; todo o resto depende desta migração.

CREATE SCHEMA staging;
COMMENT ON SCHEMA staging IS 'Área de trabalho do gerador de dados; recriada a cada carga e publicada em curated numa transação.';

CREATE SCHEMA curated;
COMMENT ON SCHEMA curated IS 'Dados fictícios finais da imobiliária Serra Clara Imóveis (modelo estrela simplificado).';

CREATE SCHEMA analytics;
COMMENT ON SCHEMA analytics IS 'Camada semântica: views de métricas e catálogo. Dashboard e agente consultam as mesmas views.';

CREATE SCHEMA app;
COMMENT ON SCHEMA app IS 'Dados da aplicação: conversas e mensagens do agente de IA.';

CREATE SCHEMA audit;
COMMENT ON SCHEMA audit IS 'Auditoria: cargas de dados e execuções do agente (ferramentas, SQL, duração, tokens, custo).';

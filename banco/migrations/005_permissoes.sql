-- INTRODUÇÃO
-- Migração 005: permissões dos três usuários de aplicação (defesa em profundidade).
--   app_dashboard -> somente leitura em analytics e nas tabelas não sensíveis de
--                    curated (sem acesso a clientes);
--   app_agente    -> idem, mais INSERT/UPDATE apenas nas tabelas de conversa e
--                    auditoria (o agente precisa registrar histórico e custos).
--                    A trava real contra escrita nos dados é a ausência de GRANT;
--                    default_transaction_read_only = on e statement_timeout = 10 s
--                    são camadas extras no caminho de consulta SQL livre;
--   app_gerador   -> escrita em staging/curated e insert em audit.cargas (carga).
-- A tabela curated.clientes NÃO recebe GRANT para ninguém além do gerador:
-- os dados pessoais fictícios existem só para provar a trava.
-- RESUMO: menor privilégio por serviço; clientes inacessível ao dashboard e ao agente.

-- --------------------------- app_dashboard ---------------------------------
GRANT USAGE ON SCHEMA analytics, curated, audit TO app_dashboard;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO app_dashboard;
GRANT SELECT ON curated.dim_cidade, curated.dim_bairro, curated.dim_equipe,
                curated.dim_corretor, curated.dim_origem, curated.dim_campanha,
                curated.dim_calendario, curated.imoveis, curated.fato_leads,
                curated.fato_visitas, curated.fato_propostas, curated.fato_negocios,
                curated.metas_mensais
    TO app_dashboard;
GRANT SELECT ON audit.cargas TO app_dashboard;  -- rodapé "Dados atualizados em"
ALTER ROLE app_dashboard SET statement_timeout = '10s';
ALTER ROLE app_dashboard SET default_transaction_read_only = on;

-- ----------------------------- app_agente ----------------------------------
GRANT USAGE ON SCHEMA analytics, curated, app, audit TO app_agente;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO app_agente;
GRANT SELECT ON curated.dim_cidade, curated.dim_bairro, curated.dim_equipe,
                curated.dim_corretor, curated.dim_origem, curated.dim_campanha,
                curated.dim_calendario, curated.imoveis, curated.fato_leads,
                curated.fato_visitas, curated.fato_propostas, curated.fato_negocios,
                curated.metas_mensais
    TO app_agente;
-- Persistência do histórico e da auditoria (único destino de escrita do agente):
GRANT SELECT, INSERT ON app.agente_conversas, app.agente_mensagens TO app_agente;
GRANT INSERT ON audit.agente_execucoes TO app_agente;
-- SELECT na própria auditoria: o teto diário de custo soma as execuções do dia.
GRANT SELECT ON audit.agente_execucoes TO app_agente;
GRANT SELECT, INSERT, UPDATE ON audit.limite_ip TO app_agente;
GRANT SELECT ON audit.cargas TO app_agente;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO app_agente;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA audit TO app_agente;
ALTER ROLE app_agente SET statement_timeout = '10s';
-- Camada extra: sessões do agente nascem somente leitura; o código de
-- auditoria usa SET TRANSACTION READ WRITE só na transação que grava
-- histórico/custos (SET LOCAL não funciona: o read-only é fixado no BEGIN).
ALTER ROLE app_agente SET default_transaction_read_only = on;

-- ----------------------------- app_gerador ---------------------------------
-- O gerador recria o schema staging a cada carga (DROP SCHEMA ... CASCADE),
-- então precisa ser o DONO dele (USAGE/ALL não bastam para DROP) e ter CREATE
-- no banco para o CREATE SCHEMA dentro da mesma operação.
ALTER SCHEMA staging OWNER TO app_gerador;
GRANT CREATE ON DATABASE analista_dados TO app_gerador;
GRANT USAGE ON SCHEMA staging, curated, audit TO app_gerador;
GRANT ALL ON ALL TABLES IN SCHEMA staging TO app_gerador;
GRANT ALL ON ALL TABLES IN SCHEMA curated TO app_gerador;
GRANT INSERT ON audit.cargas TO app_gerador;
-- UPDATE nas sequences: o gerador realinha os SERIALs com setval() após a
-- publicação (setval exige UPDATE, não apenas USAGE/SELECT).
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA curated TO app_gerador;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA staging TO app_gerador;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA audit TO app_gerador;

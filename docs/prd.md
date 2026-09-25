# 📋 PRD — autoSINAPI API: Requisitos e Escopo da API

Este documento de Requisitos de Produto (PRD) especifica as funcionalidades e comportamentos da API **autoSINAPI**.

---

## 1. Escopo Funcional (Casos de Uso)

A API fornece acesso estruturado à base de dados SINAPI através dos seguintes casos de uso:

### 1.1. Consulta e Busca de Catálogos (Insumos e Composições)
*   **Busca por Código:** Retorna detalhes completos do insumo ou composição para uma determinada UF, mês de referência e regime.
*   **Busca Textual:** Busca paginada por termo descritivo utilizando similaridade fonética e de caracteres (`unaccent` + trigrama), retornando lista de correspondências ordenadas por relevância.

### 1.2. Inteligência Analítica (Business Intelligence - BI)
*   **Bill of Materials (BOM):** Retorna a árvore hierárquica completa (explosão de subcomposições recursivas até 10 níveis) de uma composição, detalhando coeficientes acumulados e impacto financeiro de cada insumo.
*   **Man-Hours (Hora-Homem):** Calcula a soma total de coeficientes de insumos de mão de obra (unidade `'H'`) na árvore de uma composição.
*   **Curva ABC:** Identifica quais insumos representam a maior parcela de custo (Classe A: 80%, Classe B: 15%, Classe C: 5%) em um conjunto de composições.
*   **Otimizador de Custo:** Retorna os top-N insumos de maior impacto financeiro em uma composição para análise de substituição de materiais.
*   **Série Histórica e Comparativo Regional:** Evolução de preços ao longo do tempo e mapa de calor comparativo de custos entre todos os estados brasileiros.

---

## 2. Rastreabilidade de Dados e Auditoria

Seguindo as metas de qualidade do banco de dados e recuperando as diretrizes originais, a API deve expor as regras definidas no **[Regras de Rastreabilidade (data_traceability_rules.md)](./data_traceability_rules.md)**:
*   **Campos de Auditoria Obrigatórios:** Respostas de endpoints do catálogo (`insumos`, `composicoes`, etc.) devem expor as colunas `sinapi_versao`, `etl_run_id`, `created_at` e `updated_at`.
*   **Endpoint de Auditoria:** `/api/v1/public/bi/audit/{tipo_item}/{codigo}` para retornar o histórico de modificações, retificações e manutenções ocorridas no item com base nos logs de auditoria do banco.
*   **Preservação Estrutural:** O cálculo de árvores analíticas antigas (BOM) deve respeitar a estrutura histórica ativa no respectivo mês de referência consultado.

---

## 3. Segurança e Rate Limiting da API Mínima
*   A API mínima (GPLv3) opera localmente sem paywalls comerciais.
*   **Endpoints Públicos (Demo):** Operam sem necessidade de autenticação no FastAPI. O controle de cotas (rate limit de demonstração de 60 req/min e 1.000 req/mês) é configurado no gateway; a API apenas documenta o contrato.
*   **Sanitização de Input:** O parâmetro `?q=` nos endpoints de busca deve ser sanitizado para remover caracteres especiais antes de executar buscas textuais, evitando erros de sintaxe ou vulnerabilidades de SQL Injection.

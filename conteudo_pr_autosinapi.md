# 🚀 feat(etl): Evolução do Motor ETL e Hardening SSOT

## 📋 Descrição
Este PR introduz uma evolução significativa no toolkit **AutoSINAPI**, transformando-o de um extrator básico em uma plataforma de inteligência de dados. O foco principal foi eliminar "pontos cegos" identificados na auditoria e garantir a soberania de dados (SSOT).

## ✨ Alterações Principais

### 1. Enriquecimento de Dados (Data Enrichment)
- **Classificação de Insumos:** Agora o motor extrai a coluna `classificacao` das planilhas de referência.
- **Grupos de Composição:** Extração automatizada da coluna `grupo` para composições.
- **Resiliência:** Implementação de placeholders (`NAO_CLASSIFICADO`) para itens que constam na estrutura analítica mas não no catálogo.

### 2. Hardening SSOT (Inteligência de Engenharia)
- **Rastreabilidade de Preços:** Captura da coluna `origem_preco` (AS, CR, C) para identificar se o preço é pesquisado ou derivado.
- **Famílias e Coeficientes:** Adição de suporte ao arquivo `SINAPI_familias_e_coeficientes`, mapeando a hierarquia de representatividade.
- **Mix de Mão de Obra:** Captura da porcentagem de custo de MO por UF através do arquivo `SINAPI_mao_de_obra`.

### 3. Infraestrutura e Qualidade
- **Evolução do Schema:** Atualização do `Database` para incluir tabelas de famílias, coeficientes e mix de MO.
- **Correção de Testes:** Suíte de testes de integração (`test_pipeline.py`) atualizada e passando 100%.

## 📊 Impacto no Ecossistema
- **API:** Habilita filtros por categoria e badges informativos.
- **BI:** Permite análises de produtividade e curvas ABC baseadas em grupos reais da Caixa.

## ✅ Checklist de Validação
- [x] Reprocessamento histórico de 14 meses concluído localmente com este código.
- [x] 100% de cobertura nos campos de classificação e grupo após reprocessamento.
- [x] Testes de regressão validados via Pytest.

# 🛡️ Sprint: Hardening SSOT — Inteligência de Engenharia SINAPI

> **Status:** Planejada
> **Objetivo:** Transformar o AutoSINAPI de um simples extrator de tabelas em um espelho fiel da inteligência de custos da CAIXA, capturando metadados de origem de preço, coeficientes de representatividade e mix de mão de obra.

---

## 📋 Contexto
A auditoria identificou que o modelo atual descarta informações vitais que definem a confiabilidade do preço (se é pesquisado ou derivado) e a composição financeira (porcentagem de mão de obra). Esta sprint visa eliminar esses "pontos cegos".

## 🎯 Escopo da Sprint

### Tarefa 1: Captura de Metadados de Origem de Preço (Aba ISD/ICD/ISE)
**Objetivo:** Adicionar a coluna `origem_preco` à tabela `precos_insumos_mensal`.
- **Ação:** No `Processor._process_precos_sheet`, extrair a coluna "Origem de Preço".
- **Ação:** Atualizar o schema no `Database.create_tables`.

### Tarefa 2: Integração de Famílias e Coeficientes
**Objetivo:** Capturar a lógica de preços derivados (Insumos Representados).
- **Ação:** Criar nova tabela `insumos_familias` (codigo_familia, codigo_insumo, categoria).
- **Ação:** Criar nova tabela `coeficientes_familia_mensal` (codigo_insumo, uf, coeficiente, data_referencia).
- **Ação:** Implementar novo método no `Processor` para ler `SINAPI_familias_e_coeficientes_XXXX.xlsx`.

### Tarefa 3: Decomposição de Mix de Mão de Obra
**Objetivo:** Armazenar a porcentagem de mão de obra por composição e UF.
- **Ação:** Criar nova tabela `composicoes_mix_mao_de_obra` (composicao_codigo, uf, porcentagem_mo, data_referencia).
- **Ação:** Implementar novo método no `Processor` para ler `SINAPI_mao_de_obra_XXXX.xlsx`.

### Tarefa 4: Enriquecimento do Analítico (Encargos Sociais)
**Objetivo:** Capturar o campo `%AS` (Encargos Sociais) na estrutura das composições.
- **Ação:** No `Processor.process_composicao_itens`, extrair a coluna `%AS` da aba "Analítico com Custo".
- **Ação:** Adicionar coluna `percentual_as` nas tabelas de relacionamento.

## 🛠️ Alterações no Modelo de Dados (Proposta)

| Tabela | Nova Coluna | Tipo | Descrição |
|---|---|---|---|
| `precos_insumos_mensal` | `origem_preco` | VARCHAR(10) | AS, CR ou C |
| `custos_composicoes_mensal` | `percentual_mo` | NUMERIC | % de mão de obra na UF |
| `composicao_insumos` | `percentual_as` | NUMERIC | % de encargos sociais |

---

## ✅ Critérios de Aceite
1. [ ] Consulta SQL permite identificar quais insumos em SP têm preço derivado (CR).
2. [ ] É possível extrair o custo total de mão de obra de uma composição sem re-processar o analítico.
3. [ ] O pipeline não quebra caso os arquivos opcionais (Famílias/MO) estejam ausentes (Degradação Graciosa).

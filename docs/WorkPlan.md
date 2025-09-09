# Plano de Trabalho para Futuras Funcionalidades de BI

Este documento descreve o plano de implementação para as próximas funcionalidades de Business Intelligence a serem adicionadas à AutoSINAPI API.

---

### Funcionalidade 1: Análise de Produtividade

-   **Objetivo:** Detalhar o custo de uma composição em suas categorias primárias (Mão de Obra, Material, Equipamento) e calcular métricas de produtividade, como o custo por homem-hora.

-   **Plano de Implementação:**

    1.  **Schema (`api/schemas.py`):**
        -   Criar um novo schema `AnaliseProdutividade` com os campos:
            -   `custo_total: float`
            -   `percentual_mao_de_obra: float`
            -   `percentual_material: float`
            -   `percentual_equipamento: float`
            -   `total_hora_homem: float`
            -   `custo_por_hora_homem: float`

    2.  **Lógica (`api/crud.py`):**
        -   Criar a função `get_analise_produtividade(db: Session, codigo: int, ...)`.
        -   A função irá reutilizar a query de `get_composicao_bom` para obter a lista completa de insumos base e seus custos.
        -   Implementar uma lógica de **classificação** para cada insumo (Mão de Obra, Material, Equipamento). Uma heurística inicial pode ser baseada na unidade e na descrição do insumo (ex: unidade 'H' -> Mão de Obra; descrição contém 'CAMINHAO', 'BETONEIRA' -> Equipamento; o resto -> Material).
        -   Com os insumos classificados, **agregar** (somar) o `custo_impacto_total` para cada uma das três categorias.
        -   Calcular os percentuais e as métricas finais para retornar no formato do schema.

    3.  **Endpoint (`api/main.py`):**
        -   Criar o endpoint `GET /bi/composicao/{codigo}/produtividade`.
        -   O endpoint receberá o código da composição e os parâmetros de contexto (UF, data, regime).
        -   Ele chamará a função `crud.get_analise_produtividade` e retornará o resultado.

---

### Funcionalidade 2: Análise de Impacto (Where-Used Analysis)

-   **Objetivo:** Permitir que o usuário rastreie o impacto de um insumo, descobrindo todas as composições de nível superior que o utilizam, direta ou indiretamente.

-   **Plano de Implementação:**

    1.  **Schema (`api/schemas.py`):**
        -   Criar um novo schema `ComposicaoImpactada` com os campos `codigo: int` e `descricao: str`.

    2.  **Lógica (`api/crud.py`):**
        -   Criar a função `get_composicoes_impactadas_por_insumo(db: Session, codigo_insumo: int, ...)`.
        -   Esta função exigirá a implementação de uma **query recursiva reversa** (de filho para pai).
        -   A CTE (Common Table Expression) começará com o código do insumo, encontrando suas composições-pai diretas na view `vw_composicao_itens_unificados`.
        -   O passo recursivo irá então encontrar os pais dessas composições, subindo na hierarquia até que não haja mais pais.
        -   O resultado final será uma lista distinta das composições de nível superior encontradas.

    3.  **Endpoint (`api/main.py`):**
        -   Criar o endpoint `GET /bi/insumo/{codigo}/onde-usado`.
        -   O endpoint receberá o código do insumo e retornará a lista de composições impactadas.

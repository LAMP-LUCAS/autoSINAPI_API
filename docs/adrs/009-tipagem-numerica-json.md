# ADR 009 — Resposta numérica como JSON number (Decimal no cálculo, float na fronteira)

## Status
Aceito (2026-09-30) · Fase 6 da auditoria MCP de custo (STORY-MCP-007) ·/item X-01

## Contexto
A certificação funcional via MCP (2026-09-30) detectou que **AutoCUB** e **AutoINCC**
serializam todo valor numérico como **string JSON**, enquanto **AutoSINAPI** já
devolve número puro:

```jsonc
// AutoCUB — cub_calc_area
{"area_real_total_m2": "33.10", "custo_estimado_total": "102894.53", "fator_equivalente_medio": "1.0417"}

// AutoINCC — incc_correction
{"valor_inicial": "250000.00", "fator_correcao": "1.109557", "indice_inicial": "1168.327903712405700"}

// AutoSINAPI — já correto
{"custo_total": 5.51, "preco_mediano": 27.39}
```

A causa é **uma só e sistêmica**: Pydantic v2 serializa `Decimal` como `str` por
padrão (não há `field_serializer` nem `json_encoders` custom nos dois repositórios).
Todos os schemas de resposta declaram `Decimal`, e o cache Redis usa
`model_dump(mode="json")` — ou seja, os dois caminhos (frio e quente) herdam o
mesmo comportamento.

Consequências práticas para o consumidor:
- agente com structured output precisa parsear texto antes de somar/multiplicar;
- planilha e typed consumer (TypeScript/Pydantic/OpenAPI strict) quebram ou
  falham em silêncio;
- a documentação das tools não pode assumir `number`, então o agente "adivinha".

## Decisão
**Manter `Decimal` no domínio (banco, ETL, cálculos) e serializar `float` apenas
na fronteira JSON.** A conversão é feita por um **tipo anotado compartilhado**,
não campo a campo:

```python
# app/domain/tipos.py (um por repositório, mesmo nome e semântica)
Num = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
```

Regras que acompanham a decisão:
1. **Cálculo continua em `Decimal`** — nada de `float` em regra de negócio
   (fator de correção, CUB/m², índice oficial). A perda de precisão, se houver, ocorre só na serialização.
2. **Datas continuam string ISO** (`date`/`datetime` do Pydantic) — inalterado.
3. **A regra é documentada** no guia de regras de negócio de cada repositório
   (AutoCUB: `docs/GUIA_ENDPOINTS_E_REGRAS_DE_NEGOCIO.md`).
4. **A tool MCP avisa o agente** — a descrição da tool declara explicitamente que
   valores numéricos chegam como número JSON (`number`), para o agente não
   assumir string (exigência do requisito de clareza da ferramenta).
5. **`inicio_serie` permanece `str`** (AutoINCC) por contrato já documentado
   (aceita `''`); não é valor numérico de cálculo.

## Consequências
* **Positivas**
  * Contrato único entre as três APIs (`number` para todo valor numérico);
  * consumidores tipados funcionam; `assert isinstance(x, (int, float))` passa;
  * precisão decimal preservada em banco, ETL e regra de negócio.
* **Negativas / riscos**
  * `float` tem ~15–17 dígitos significativos: os índices `Numeric(38,15)`
    (AutoINCC `numero_indice`) perdem as casas finais **na serialização**. Aceito
    porque o consumidor é humano/agente/planilha, não um replicador contábil;
    quem precisar de precisão exata usa a fonte (SGS) ou o banco.
  * Testes de contrato que afirmavam string passam a falhar — são **atualização
    legítima** (ex.: `autoINCC_API/tests/test_api.py` afirma
    `data["valor_inicial"] == "100000.00"`), não regressão.
  * Cache Redis: como usa `model_dump(mode="json")`, a mudança vale para o cache
    junto — **exige flush das camadas de cache na ativação**.

## Referências
* STORY-MCP-007 (certificação funcional) — item X-01.
* ADR-004 (busca trigram) — mesma política de "o banco é a fonte; a API
  entrega o tipo que o consumidor precisa".
* Issue Live: medição ao vivo em 2026-09-30 (todos os campos numéricos de
  `incc_correction` e `cub_calc_area` observados como `str`).

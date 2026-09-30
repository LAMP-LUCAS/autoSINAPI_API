# ADR 010 — Falhar alto: entrada inválida e resultado parcial nunca são silêncio

## Status
Aceito (2026-09-30) · Fase 6 da auditoria MCP de custo (STORY-MCP-007) ·/itens S-01, S-03, S-04, C-01, C-04

## Contexto
A certificação funcional via MCP (2026-09-30) mostrou três modos de falha que
**não sinalizam erro** ao agente, embora o resultado esteja errado:

1. **Entrada inválida aceita.** `uf:"XX"`, `data_referencia:"2030-01"` e
   `q:"xyzabc"` respondem `200` com `{"items": [], "total": 0}`. O agente não
   distingue "não existe" de "filtro restritivo demais" — e conclude errado.
2. **Resultado parcial silencioso.** `sinapi_get_curva_abc([99803, 4750])` devolve
   a curva **só** de 99803, com `isError:false`: 4750 (PEDREIRO) é *insumo*, não
   composição, e é descartado sem aviso. O agente acredita que a curva cobre os
   dois códigos.
3. **Ausência de dado sem texto.** `cub_get_uf(uf="AC", ano=2026, mes=7)`
   responde `isError:false`, `structuredContent: {"result": []}` e
   `content: []` — **zero blocos**. Qualquer cliente que leia `content` vê branco,
   sem "sem dados para AC em 2026-07". Mesmo defeito em `cub_calc_area` para UF
   sem CUB: `custo_estimado_total: null` sem motivo irmão.

O padrão já vigente no repositório é o oposto: erro carrega `correlation_id`
(claim §5.x do gate) e ausência de dado já tem precedente próprio — a nota
**LIM-38** ("dado não disponibilizado pelo CBIC") que responde em vez de propagar
erro. Esta ADR generaliza esse precedente.

## Decisão
Três estados distintos, com semântica explícita — **nunca o mesmo código para
"não achei" e "você errou"**:

| Estado | HTTP | Corpo | Exemplo |
|---|---|---|---|
| **Ausência de dado** (entrada válida, nada a retornar) | `200` | envelope **não vazio**: `items: []`, contadores, `motivo`, `dica` | `search("xyzabc")` → `{items: [], total: 0, meta: {did_you_mean: "concreto"}}` |
| **Entrada inválida** (fora do domínio) | `400`/`422` | erro nomeado + **valor válido mais próximo** | `uf:"XX"` → `INVALID_UF`, lista das 27 siglas |
| **Entrada válida sem resolução** (código/UF/período não encontrado) | `404` | erro nomeado + **o que foi pedido** | `get_audit(insumo, 4750, 2026-08)` → `AUDIT_NOT_FOUND` + última data com evento |

Regras que acompanham a decisão:
1. **Um resultado parcial é erro.** Se o agente pediu N códigos e só M
   resolveram, responde-se erro nomeado listando quais não resolveram — nunca
   `200` com o subconjunto. (Aplica-se a `curva_abc`.)
2. **Ausência de dado sempre tem envelope com texto.** Nenhuma tool pode
   responder com `content: []`; o `structuredContent` e o `content` são
   coerentes entre si. (Aplica-se ao AutoCUB, que é onde o vazio mudo existe.)
3. **Erro sempre com `correlation_id`** (regra já existente, mantida).
4. **Validação no limite, não no interior.** Sigla de UF, formato e janela de
   `data_referencia` e tipo de item são validados na borda (router/tool) para que
   o erro chegue ao agente antes de tocar o banco.
5. **Mensagem de erro nomeia o item real.** O rótulo do erro usa o `tipo_item`
   recebido, nunca um literal fixo (defeito S-05: "onde-é-usado do **insumo** X"
   para uma consulta de **composição**).

## Consequências
* **Positivas**
  * O agente distingue "não achei" de "você errou" e pode pedir `did_you_mean`;
  * Nenhum resultado parcial silencioso chega a um orçamento;
  * Ausência de dado vira texto autoconsciente (`motivo`, `dica`), compatível
    com a philosophy LIM-38 já adotada;
  * `correlation_id` rastreia a falha ponta a ponta.
* **Negativas / riscos**
  * Quebra clientes que dependiam do vazio silencioso (nenhum interno ao gate);
  * `400` em `uf:"XX"` é mais rígido que antes — clientes passes devem corrigir;
  * Exige atualizar testes de contrato que afirmavam `total: 0` para entrada
    inválida.

## Referências
* STORY-MCP-007 (certificação funcional) — itens S-01, S-03, S-04, S-05, C-01, C-04.
* Lim-38 (`autocub_api/autocub/api/lim38.py`) — precedente de "responder com nota".
* ADR-004 (busca trigram) — base do `did_you_mean` (a busca já tolera erro de
  digitação; a suggestion expõe isso ao agente).
* Medição ao vivo 2026-09-30 nos gateways `mcp-autosinapi` / `mcp-autocub`.

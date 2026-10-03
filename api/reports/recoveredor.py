"""api/reports/recoveredor.py — quem entra no 3º slot (recuperação e promoção).

Duas regras que não podem ser o "mesmo workflow com nome diferente":

**Recuperação (winback)** — disparada por **falta de consumo**, não por data.
Consumo é uso de API **e** leitura do portal: quem só lê a KB toda semana e
nunca chama a API está ativo, e receber winback seria dizer "voltamos porque
você parou" para alguém que não parou.

Marcos em 30 e 45 dias sem consumo. O segundo só existe se o primeiro não
reconvenceu — por isso o guard de "já enviou a etapa 1".

**Promoção** — só para quem **não paga**. Promover pagante ativo é jogar fora
a única receita que existe e ainda desvalorizar o plano. E é espaçada: no
máximo a cada 15 dias, com padrão bimestral, porque promoção frequente cansa
e ainda rouba a atenção do conteúdo.

Nenhuma das duas marca o lead como `lost`: `lost` é decisão comercial, não
efeito colateral de e-mail nonEnviar.
"""

from __future__ import annotations

import datetime as _dt
import logging
from decimal import Decimal
from typing import Optional, Sequence

from .grade import PROMO_MIN_DIAS, PROMO_PADRAO_DIAS

logger = logging.getLogger("autosinapi.reports.recuperacao")

# Marcos de recuperação: dias sem consumo → envio.
MARCOS_WINBACK = (30, 45)
STEP_WINBACK = {30: "winback_30d", 45: "winback_45d"}
STEP_PROMO = "promo"

# Follow-ups do nurture (D3/D7): são conteúdo de relacionamento, mas não
# pertencem nem à trilha de relatórios nem à de artigos. Sem eles listados,
# a classificação por exclusão os virava "relatório".
STEP_NURTURE = ("d3", "d7")


# Passos de controle: existem na `nurture_state`, mas não são conteúdo da
# trilha (nem relatório, nem artigo). Sem esta lista, a regra "não é relatório
# logo é artigo" classificaria recuperação, promoção e follow-up como artigo —
# e um lead com relatório + winback destravaria promoção sem nunca ter recebido
# um artigo da KB.
PASSOS_CONTROLE = (STEP_PROMO, *STEP_WINBACK.values(), *STEP_NURTURE)


def _e_relatorio(step: str) -> bool:
    """O passo é uma das chaves de relatório do registro?

    As chaves são a SSOT do que existe como relatório (`incc_leitura_mes`,
    `cub_dispersao`, `sinapi_foco_custo`, ...).
    """
    from . import registro
    return step in registro.implementados()


def _e_artigo(step: str) -> bool:
    """O passo é artigo da base de conhecimento?

    Dois formatos convivem na `nurture_state`, porque vêm de dois códigos:

    * `kb_01`, `kb_02` — o rótulo sequencial de `kb_sequence.step_para`,
      usado pela trilha de artigo (`kb_admin`);
    * o **slug** cru (`analise-tendencia-preco-insumos`) — o que o slot de
      artigo do `crm_conteudo` grava, já que `UNIQUE (lead_id, step)` é o
      que garante "um artigo, uma vez" e o slug é o identificador estável
      do conteúdo.

    Reconhecer só o prefixo `kb_` faz um lead que recebeu artigo real contar
    como "nunca recebeu artigo" — foi assim que a primeira promoção nunca
    destravou.
    """
    if step.startswith("kb_"):
        return True
    return (not _e_relatorio(step)) and step not in PASSOS_CONTROLE


def _int(v) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _d(v) -> Optional[_dt.date]:
    try:
        return v.date() if hasattr(v, "date") and callable(getattr(v, "date")) else (
            _dt.date.fromisoformat(str(v)[:10]) if v else None)
    except (ValueError, TypeError):
        return None


class ContextoRecuperacao:
    """O que a decisão precisa saber sobre um lead/cliente.

    Montado a partir da base pelo `api.crm_conteudo`; aqui só a regra, para
    ficar testável sem banco.
    """

    def __init__(self, *, lead_id: str, email: str, eh_cliente_pagante: bool,
                 dias_sem_consumo_api: Optional[int],
                 dias_sem_consumo_portal: Optional[int],
                 dias_sem_consumo_app: Optional[int] = None,
                 etapas_enviadas: Sequence[str] = (),
                 consentimento: bool = True,
                 dias_sem_promocao: Optional[int] = None,
                 hoje: Optional[_dt.date] = None):
        self.lead_id = lead_id
        self.email = email
        self.eh_cliente_pagante = eh_cliente_pagante
        self.dias_sem_consumo_api = dias_sem_consumo_api
        self.dias_sem_consumo_portal = dias_sem_consumo_portal
        self.dias_sem_consumo_app = dias_sem_consumo_app
        self.etapas_enviadas = tuple(etapas_enviadas)
        self.consentimento = consentimento
        # Dias desde a última promoção. `None` = nunca houve.
        self.dias_sem_promocao = dias_sem_promocao
        self.hoje = hoje or _dt.date.today()

    @property
    def dias_sem_consumo(self) -> Optional[int]:
        """O sinal **mais recente** entre os três canais — atividade em
        qualquer um significa lead ativo.

        Antes isto era o **mínimo** entre API e portal. **A primeira redação
        deste texto dizia que o degrau de 45 dias era "inalcançável por
        construção" porque o `created_at` congelaria o valor. Era falso, e a
        medição refutou**: `now() - created_at` cresce todo dia, então um lead
        de 41 dias chega a 45 normalmente (cenário de 46 dias devolve
        `winback_45d` sem código novo). O que a cascata corrige é o **oposto**
        — impede que um canal envelhecido, sem atividade real, semee um
        winback para quem está ativo em outro canal.

        Cascata decidida em 03/10 (usuário):

        | sinal | peso | por quê |
        |---|---|---|
        | app (login) | **canônico** | é o que é pago e o que vale |
        | consumo de API | canônico | é uso real do produto |
        | portal | chance de escape | quem não entra no app mas navega pelo site não é inativo |

        **Limitação medida, não escondida:** `SQL_CONSUMO_APP` é idêntica a
        `SQL_CONSUMO_PORTAL` (mesmo sha1) porque **não existe evento de login
        em lugar nenhum** — `leads.last_activity_at` só é movido pela ponte de
        envio de formulário e por ação manual. Nos 32 leads reais a cascata
        diverge do `min(api, portal)` em **zero** casos: é um no-op hoje e só
        começa a valer quando o app emitir sinal próprio. O filtro de
        negativos já vale — clock adiantado não vira "ativo há 400 dias".
        """
        vals = [v for v in (self.dias_sem_consumo_api,
                             self.dias_sem_consumo_app,
                             self.dias_sem_consumo_portal)
                if v is not None and v >= 0]
        return min(vals) if vals else None

    @property
    def dias(self) -> Optional[int]:
        """Alias de `dias_sem_consumo` — é o que o `decidir` consulta.

        Nome curto porque é o dado que toda a decisão lê: `dias = c.dias` e
        compara com o degrau. Duas propriedades com o mesmo cálculo invites
        a divergirem; aqui uma só.
        """
        return self.dias_sem_consumo

    def ja_enviou(self, step: str) -> bool:
        return step in self.etapas_enviadas

    @property
    def trilha_completada(self) -> bool:
        """Já atravessou um ciclo inteiro da trilha de conteúdo.

        Um ciclo é **relatório + artigo**: os dois-touchpoints que a trilha
        entrega por semana. Exigir os dois antes da primeira promoção é o que
        dá "histórico" ao corte sem criar impasse — exigir histórico de
        promoção seria circular, porque a primeira é justamente a que cria o
        histórico.

        A classificação é **positiva** (cada passo é do que ele é), não por
        exclusão. A versão anterior fazia `any(not p.startswith("kb_"))` para
        achar relatório, o que errava dos dois lados: o artigo gravado como
        slug (`analise-tendencia-preco-insumos`) não era artigo, e `d3` era
        relatório.
        """
        passos = set(self.etapas_enviadas)
        return (any(_e_artigo(p) for p in passos)
                and any(_e_relatorio(p) for p in passos))


def decidir_winback(c: ContextoRecuperacao) -> Optional[str]:
    """Passo de recuperação a enviar, ou `None`.

    `None` é o caso comum: ativo, sem consentimento, pagante Recoverido, ou
    nenhum marco atingido.
    """
    if not c.consentimento:
        return None
    if c.eh_cliente_pagante:
        # Cliente que paga não é perdido. Não entra em recuperação.
        return None

    dias = c.dias_sem_consumo
    if dias is None:
        return None

    for marco in MARCOS_WINBACK:
        if dias >= marco and not c.ja_enviou(STEP_WINBACK[marco]):
            return STEP_WINBACK[marco]
    return None


def decidir_promo(c: ContextoRecuperacao) -> Optional[str]:
    """Passo de promoção a enviar, ou `None`.

    Recusa pagante ativo sempre: a receita existe, e a promoção seria o oposto
    devalorizar o plano.
    """
    if not c.consentimento:
        return None
    if c.eh_cliente_pagante:
        return None
    if c.ja_enviou(STEP_PROMO):
        return None

    dias = c.dias_sem_promocao
    if dias is None:
        # Primeira promoção: só depois de um ciclo completo da trilha. Antes
        # disso a pessoa nunca recebeu nada nosso, e promoção para lead frio é
        # exatamente o e-mail que marca spam.
        return STEP_PROMO if c.trilha_completada else None
    return STEP_PROMO if dias >= PROMO_PADRAO_DIAS else None


def promo_permite_hoje(dias_sem_promocao: Optional[int]) -> bool:
    """Espaçamento mínimo. Separado da decisão para ser testável sozinho."""
    if dias_sem_promocao is None:
        return False
    return dias_sem_promocao >= PROMO_MIN_DIAS


__all__ = ["MARCOS_WINBACK", "STEP_WINBACK", "STEP_PROMO", "STEP_NURTURE",
           "PASSOS_CONTROLE", "ContextoRecuperacao", "decidir_winback",
           "decidir_promo", "promo_permite_hoje"]

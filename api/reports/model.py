"""api/reports/model.py — o contrato de um relatório, sem I/O.

Nenhuma classe aqui toca banco, rede ou arquivo. O relatório é um **valor**:
o mesmo `Relatorio` sempre produz o mesmo HTML. É o que permite comparar com o
anterior e **pular** em vez de reenviar quando o dado não mudou — sem isso,
"informação nova" é promessa sem verificação.

Os números vêm de `Decimal`: arredondar float em Python acumula erro de
binário, e num relatório de custo um centésimo decide entre "acabou de virar"
e "não virou".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional, Sequence


class Formato(Enum):
    """Como o relatório é apresentado. Todos vão no e-mail.

    `TABELA` é a fonte da verdade: legível em qualquer cliente, terminal ou
    leitor de tela. `TEXTO` atende quem escaneia. `GRAFICO` reforça — nunca é
    o único portador do número, porque SVG inline não é renderizado em
    cliente que bloqueia ou tem sanitizador próprio.
    """

    TABELA = "tabela"
    TEXTO = "texto"
    GRAFICO = "grafico"


class Categoria(Enum):
    """Agrupa para escolher o *gatilho*, não o assunto editorial.

    Serve para uma coisa só: saber se o relatório depende do pipeline que já
    existe. `BASE` e `SISTEMA` disparam por evento ETL (fora do carril);
    `INSIGHT` é calculado e ocupa o dia fixo.
    """

    INSIGHT = "insight"        # calculado, ocupa a grade semanal
    BASE = "base"              # competência nova (SINAPI/CUB)
    NOTA = "nota"              # rodapé, não ocupa slot


@dataclass(frozen=True)
class Metrica:
    """Um número com rótulo e contexto."""

    rotulo: str
    valor: str                      # já formatado para o cliente final
    detalhe: Optional[str] = None   # ex.: "vs +0,61% em julho"
    destaque: bool = False          # número principal do relatório
    variacao: Optional[str] = None  # sinal +/− para leitura rápida

    def linha_tabela(self) -> tuple[str, str, str]:
        return self.rotulo, self.valor, self.detalhe or ""


@dataclass(frozen=True)
class Serie:
    """Sequência temporal para o gráfico.

    `em_percentual` diz como o eixo é rotulado, e precisa ser explícito porque
    as séries do mesmo relatório têm unidades diferentes: INCC-M é um índice
    (1.296,33) e a variação mensal é uma taxa (0,66%). Tratar tudo como taxa
    rotula o índice como "129.633,00%"; tratar tudo como número rotula a taxa
    como "0,01". Com as duas coisas no mesmo relatório, adivinhar é erro
    garantido.
    """

    rotulo: str
    pontos: Sequence[tuple[str, Decimal]]
    sufixo: str = ""
    em_percentual: bool = True

    @property
    def vazia(self) -> bool:
        return len(self.pontos) < 2

    def valores(self) -> Sequence[Decimal]:
        return [v for _, v in self.pontos]


@dataclass(frozen=True)
class Bloco:
    """Um trecho: parágrafo de leitura e/ou tabela de números."""

    metricas: Sequence[Metrica] = ()
    texto: Optional[str] = None
    nota: Optional[str] = None      # rodapé discreto (fonte, competência)

    @property
    def tem_metrica(self) -> bool:
        return any(m.valor for m in self.metricas)


@dataclass(frozen=True)
class Relatorio:
    """Um relatório completo, pronto para renderizar.

    `chave` é o identificador estável (ex.: `incc_leitura_mes`). É ela que vai
    para `nurture_state.step` — e é o que impede o mesmo relatório duas vezes
    para o mesmo lead.
    """

    chave: str
    titulo: str
    resumo: str                     # a conclusão, não o dado
    blocos: Sequence[Bloco] = ()
    series: Sequence[Serie] = ()
    categoria: Categoria = Categoria.INSIGHT
    rodape: Optional[str] = None

    @property
    def tem_grafico(self) -> bool:
        return any(not s.vazia for s in self.series)

    def assinatura(self) -> str:
        """Impressão digital do *conteúdo*, não da data.

        Dois relatórios com os mesmos números têm a mesma assinatura, mesmo
        gerados em datas diferentes. É isso que permite dizer "não mudou,
        não mando" mesmo com a data no rodapé.
        """
        partes = [self.chave, self.titulo, self.resumo]
        for b in self.blocos:
            partes.append(b.texto or "")
            partes.extend(f"{r}|{v}|{d}" for r, v, d in
                          (m.linha_tabela() for m in b.metricas))
        return "|".join(partes)


@dataclass(frozen=True)
class Contexto:
    """Quem recebe e o que já recebeu."""

    lead_id: str
    email: str
    nome: str
    persona: Optional[str] = None
    eh_cliente: bool = False           # tem assinatura ativa
    dias_de_relacionamento: int = 0
    etapas_enviadas: Sequence[str] = ()
    consentimento_marketing: bool = True
    # Assinatura do último relatório de conteúdo enviado. Permite a segunda
    # trava do roteiro: competência "nova" cujo conteúdo é idêntico ao
    # anterior não sai — sem isso, "competência nova" viraria atalho para
    # reenviar a mesma informação com outro rótulo.
    ultima_assinatura: Optional[str] = None

    @property
    def segmento(self) -> str:
        """`novo` (<30d), `madura` (lead antigo) ou `cliente` (assina)."""
        if self.eh_cliente:
            return "cliente"
        return "novo" if self.dias_de_relacionamento < 30 else "madura"

    def ja_enviou(self, chave: str) -> bool:
        return chave in self.etapas_enviadas


@dataclass(frozen=True)
class Decisao:
    """O que o pipeline decidiu, e por quê."""

    enviar: bool
    relatorio: Optional[Relatorio] = None
    motivo: str = ""
    slot: Optional[str] = None        # 'enriquecimento' | 'artigo' | None


DESTAQUES_MAX = 3

__all__ = ["Formato", "Categoria", "Metrica", "Serie", "Bloco",
           "Relatorio", "Contexto", "Decisao", "DESTAQUES_MAX"]

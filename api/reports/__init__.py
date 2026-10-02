"""api/reports — relatórios determinísticos para o e-mail de enriquecimento.

Três camadas, sem dependência entre elas:

    fontes.py  →  números (SQL)         -toucha o banco
    charts.py  →  SVG                   -função pura
    render.py  →  HTML de e-mail        -função pura
    model.py   →  o valor               -nem I/O nem lógica

A separação é o que torna a regra testável: `_montar` em `fontes.py` recebe
as linhas prontas, então verificar que "acelerando" sai quando a variação
sobe não exige popular o INCC.

Nada chama LLM. A frase do resumo é montada por condição sobre o número — é
por isso que o mesmo dado produz o mesmo relatório sempre, e que "não mudou,
não mando" é verificável em vez de palpite.
"""

from .model import (Bloco, Categoria, Contexto, Decisao, DESTAQUES_MAX,
                    Formato, Metrica, Relatorio, Serie)

__all__ = ["Bloco", "Categoria", "Contexto", "Decisao", "DESTAQUES_MAX",
           "Formato", "Metrica", "Relatorio", "Serie"]

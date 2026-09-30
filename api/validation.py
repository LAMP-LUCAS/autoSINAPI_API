"""
Validação de entrada pública — ADR 010 (falhar alto).

Three states, never conflated (see `docs/adrs/010-falhar-alto-entrada-invalida.md`):

| State                                   | HTTP | Body                                  |
|-----------------------------------------|------|---------------------------------------|
| absence of data (valid input, no rows)  | 200  | non-empty envelope (`motivo`, contadores) |
| invalid input (outside the domain)      | 400  | named error (`INVALID_UF`, …)         |
| valid input that does not resolve       | 404  | named error + what was asked          |

The `detail` is a **string** prefixed with the error code, so every client in the
ecosystem (MCP `client.py` of the three products, curl, planilha) can read it
without special-casing a JSON object.
"""
from __future__ import annotations

import re
from typing import Optional

# As 27 siglas brasileiras — mesma fonte de `autocub/api/lim38.py` (IBGE).
BR_UFS = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
})

_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_TIPOS_ITEM = ("insumo", "composicao")


class EntradaInvalida(ValueError):
    """Entrada fora do domínio — vira 400 com código nomeado."""

    status_code = 400

    def __init__(self, codigo: str, mensagem: str, **extra: object):
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem
        self.extra = extra

    @property
    def detail(self) -> str:
        return str(self)


class NaoResolvido(EntradaInvalida):
    """Entrada válida que não resolve — vira 404 com código nomeado."""

    status_code = 404


def validar_uf(uf: str, campo: str = "uf") -> str:
    """Sigla de UF válida (2 letras, uma das 27)."""
    sigla = (uf or "").strip().upper()
    if sigla not in BR_UFS:
        raise EntradaInvalida(
            "INVALID_UF",
            f"{campo}='{uf}' não é uma UF brasileira. Use uma das 27 siglas: "
            f"{', '.join(sorted(BR_UFS))}.",
            uf=uf,
        )
    return sigla


def validar_data_referencia(
    data: str,
    *,
    max_ref: Optional[str] = None,
    campo: str = "data_referencia",
) -> str:
    """`AAAA-MM` dentro da competência publicada (nunca futura, nunca ausente)."""
    valor = (data or "").strip()
    if not _MES.match(valor):
        raise EntradaInvalida(
            "INVALID_DATE_REFERENCE",
            f"{campo}='{data}' fora do formato AAAA-MM (ex.: 2026-08).",
            data_referencia=data,
        )
    if max_ref and valor > max_ref:
        raise EntradaInvalida(
            "INVALID_DATE_REFERENCE",
            f"{campo}='{valor}' é posterior à competência mais recente "
            f"disponível ({max_ref}). Use uma referência até {max_ref}.",
            data_referencia=valor,
            max_data_referencia=max_ref,
        )
    return valor


def validar_tipo_item(tipo: str, campo: str = "tipo_item") -> str:
    """`insumo` ou `composicao` (minúsculo, canônico)."""
    valor = (tipo or "").strip().lower()
    if valor not in _TIPOS_ITEM:
        raise EntradaInvalida(
            "INVALID_TIPO_ITEM",
            f"{campo}='{tipo}' inválido. Use 'insumo' ou 'composicao'.",
            tipo_item=tipo,
        )
    return valor


def validar_contexto(
    uf: str,
    data_referencia: str,
    *,
    max_ref: Optional[str] = None,
) -> tuple[str, str]:
    """Atalho dos dois validadores usados por toda consulta contextual."""
    return (
        validar_uf(uf),
        validar_data_referencia(data_referencia, max_ref=max_ref),
    )


def nao_resolvido(codigo: str, mensagem: str, **extra: object) -> NaoResolvido:
    """Atalho para 404 nomeado (entrada válida, sem resultado)."""
    return NaoResolvido(codigo, mensagem, **extra)

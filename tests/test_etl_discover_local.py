"""§3.8 da auditoria (P1) — Smart Discovery do ETL: zips retificados não podem
matar o pipeline (RED comportamental; gate da casa `verify_mcp_audit_claims.py`
falha com `datas` faltando 2026-01 e 2026-02).

Causa-raiz provada: `PipelineETL._discover_local_files` extraía o zip em
`extraction_path` e **recursava** (`return self._discover_local_files()`).
Zips NORMAIS (ex.: 2026_03) são planos → `iterdir()` acha
`SINAPI_Referência_*.xlsx` no nível 0 e a recursão termina. Zips RETIFICADOS
(ex.: `SINAPI-2026-01-formato-xlsx_Retificacao01.zip`) extraem com PASTA
INTERNA → o xlsx fica 2 níveis abaixo, `iterencia` nunca acha nada e o ETL
entra em recursão infinita (`RecursionError` aos ~1000 frames) — exatamente o
crash que deixou 2026-01/02 sem dados.

RED: o teste abaixo reprova com `RecursionError` (hoje) e vira GREEN com a
correção: busca recursiva dos xlsx + extração com uma única nova varredura
(nunca recursão sem limite).

Ambiente: host, `PYTHONPATH=AutoSINAPI`; `DOCKER_ENV` dummy para o `__init__`
do pipeline (não conecta em nada — só lê env).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from autosinapi.etl_pipeline import PipelineETL


@pytest.fixture
def pipeline(tmp_path, monkeypatch) -> PipelineETL:
    monkeypatch.setenv("DOCKER_ENV", "true")
    monkeypatch.setenv("POSTGRES_DB", "t")
    monkeypatch.setenv("POSTGRES_USER", "t")
    monkeypatch.setenv("POSTGRES_PASSWORD", "t")
    monkeypatch.setenv("PG_HOST", "localhost")
    p = PipelineETL(run_id="test-discover")
    p.config.DOWNLOAD_DIR = str(tmp_path)
    p.config.YEAR = 2026
    p.config.MONTH = 1
    return p


def _zip_com_pasta_interna(month_dir: Path) -> Path:
    """Zip no formato retificado: xlsx dentro de pasta interna `SINAPI-...`."""
    zip_path = month_dir / "SINAPI-2026-01-formato-xlsx_Retificacao01.zip"
    internos = [
        "SINAPI_Referência_2026_01.xlsx",
        "SINAPI_mao_de_obra_2026_01.xlsx",
        "SINAPI_Manutenções_2026_01.xlsx",
        "SINAPI_familias_e_coeficientes_2026_01.xlsx",
    ]
    with zipfile.ZipFile(zip_path, "w") as zf:
        for nome in internos:
            zf.writestr(f"SINAPI-2026-01-formato-xlsx/{nome}", b"PK\x05\x06" + b"\x00" * 18)
    return zip_path


def _zip_plano(month_dir: Path) -> Path:
    """Zip normal (ex.: 2026_03): xlsx na raiz do zip."""
    zip_path = month_dir / "SINAPI-2026-01-formato-xlsx.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("SINAPI_Referência_2026_01.xlsx", b"PK\x05\x06" + b"\x00" * 18)
        zf.writestr("SINAPI_mao_de_obra_2026_01.xlsx", b"PK\x05\x06" + b"\x00" * 18)
    return zip_path


def test_zip_retificado_com_pasta_interna_nao_recurse(pipeline, tmp_path):
    """§3.8 RED: hoje explode em RecursionError; deve devolver o xlsx."""
    month_dir = tmp_path / "2026_01"
    month_dir.mkdir()
    _zip_com_pasta_interna(month_dir)

    ref, extra = pipeline._discover_local_files()

    assert ref is not None, "zip retificado com pasta interna deve fornecer a Referência (§3.8)"
    assert "refer" in ref.name.lower()
    assert extra.get("mao_de_obra") is not None, "mao_de_obra deve ser classificada"


def test_zip_plano_continua_funcionando(pipeline, tmp_path):
    """Pin do caminho que já funcionava (zips normais, ex.: 2026_03)."""
    month_dir = tmp_path / "2026_01"
    month_dir.mkdir()
    _zip_plano(month_dir)

    ref, extra = pipeline._discover_local_files()

    assert ref is not None
    assert "refer" in ref.name.lower()
    assert extra.get("mao_de_obra") is not None


def test_sem_nada_retorna_vazio_sem_travar(pipeline, tmp_path):
    """Sem zip e sem extração: devolve (None, {}) — nunca recursão/hang."""
    (tmp_path / "2026_01").mkdir()

    ref, extra = pipeline._discover_local_files()

    assert ref is None
    assert extra == {}


def test_descobre_pasta_ja_extraida_retificada(pipeline, tmp_path):
    """Cenário do volume real: pasta extraída com sufixo `_Retificacao01`
    já existe no diretório do mês — deve ser achada sem novo zip."""
    month_dir = tmp_path / "2026_01"
    extraida = month_dir / "SINAPI-2026-01-formato-xlsx_Retificacao01" / "SINAPI-2026-01-formato-xlsx"
    extraida.mkdir(parents=True)
    (extraida / "SINAPI_Referência_2026_01.xlsx").write_bytes(b"")

    ref, extra = pipeline._discover_local_files()

    assert ref is not None, "pasta retificada já extraída deve ser descoberta (§3.8)"
    assert "refer" in ref.name.lower()

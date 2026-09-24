# api/legal_service.py
"""
Serviço para gerenciar e servir documentos legais consolidados (SSOT YAML + Markdown).
Suporta stripping de frontmatter/drafts e substituição dinâmica com codificação UTF-8.
"""

import os
import re
import yaml
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.getenv("LEGAL_CONFIG_PATH", str(_REPO_ROOT / "config" / "legal_ssot.yaml")))
DOCS_DIR = Path(os.getenv("LEGAL_DOCS_DIR", str(_REPO_ROOT / "legal_docs")))


def load_legal_ssot() -> dict:
    """Carrega o SSOT YAML versionado no repositório da API."""
    path = Path(CONFIG_PATH)
    if not path.exists():
        return {"company": {}}

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"company": {}}


def clean_markdown_draft_notices(content: str) -> str:
    """Remove blocos de avisos DRAFT (linhas iniciando com '>') e cabeçalhos Frontmatter (--- ... ---)."""
    # Remove avisos DRAFT iniciais
    content = re.sub(r'^\s*>\s*.*?(\n|$)', '', content, flags=re.MULTILINE)
    # Remove bloco Frontmatter YAML
    content = re.sub(r'^\s*---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)
    return content.strip()


def get_legal_document(doc_name: str) -> dict:
    """
    Lê o documento markdown solicitado, remove frontmatter/drafts, injeta os valores do SSOT
    e retorna o conteúdo populado com metadados.
    """
    valid_docs = {
        "privacidade": "PRIVACIDADE_LGPD.md",
        "tos": "TOS.md",
        "reembolso": "REEMBOLSO.md",
        "sinapi": "SINAPI_TERMOS.md",
    }

    if doc_name not in valid_docs:
        raise ValueError(f"Documento legal '{doc_name}' não encontrado.")

    filename = valid_docs[doc_name]
    doc_path = Path(DOCS_DIR) / filename
    if not doc_path.exists():
        raise FileNotFoundError(f"Arquivo do documento {filename} não encontrado.")

    with open(doc_path, "r", encoding="utf-8") as f:
        raw_content = f.read()

    cleaned_content = clean_markdown_draft_notices(raw_content)

    ssot = load_legal_ssot()
    company = ssot.get("company", {})

    number_id = company.get("number_id", company.get("cnpj", ""))

    replacements = {
        "{{ company.legal_name }}": company.get("legal_name", ""),
        "{{ company.trade_name }}": company.get("trade_name", ""),
        "{{ company.number_id }}": number_id,
        "{{ company.cnpj }}": number_id,
        "{{ company.address }}": company.get("address", ""),
        "{{ company.city }}": company.get("city", ""),
        "{{ company.state }}": company.get("state", ""),
        "{{ company.postal }}": company.get("postal", ""),
        "{{ company.support_email }}": company.get("support_email", ""),
        "{{ company.billing_email }}": company.get("billing_email", ""),
        "{{ company.dpo_email }}": company.get("dpo_email", ""),
        "{{ company.website }}": company.get("website", ""),
        "{{ company.jurisdiction }}": company.get("jurisdiction", ""),
        "{{ company.effective_date }}": company.get("effective_date", ""),
        "{{ company.update_date }}": company.get("update_date", ""),
        "[RAZAO_SOCIAL]": company.get("legal_name", ""),
        "[CNPJ]": number_id,
        "[CPF_OU_CNPJ]": number_id,
        "[ENDERECO]": company.get("address", ""),
        "[CIDADE]": company.get("city", ""),
        "[ESTADO]": company.get("state", ""),
        "[CEP]": company.get("postal", ""),
        "[EMAIL_DPO]": company.get("dpo_email", ""),
        "[DATA]": company.get("update_date", company.get("effective_date", "")),
    }

    populated_content = cleaned_content
    for placeholder, value in replacements.items():
        populated_content = populated_content.replace(placeholder, str(value))

    return {
        "doc_name": doc_name,
        "filename": filename,
        "ssot_used": company,
        "content_markdown": populated_content,
    }

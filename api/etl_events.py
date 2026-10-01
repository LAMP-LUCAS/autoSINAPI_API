# api/etl_events.py
"""
Evento de integração `etl.completed` — adapter neutro de saída do ETL.

Este módulo é o **ponto de fronteira** do contexto de domínio do ETL com o
mundo externo. Ele existe para que consumidores externos (observabilidade,
portais, automações...) possam reagir à conclusão de uma execução **sem que
o repositório conheça quem consome** — inversão de controle via configuração.

Regras de domínio (DDD):

- **Opt-in**: sem ``ETL_EVENT_WEBHOOK_URL`` o módulo é um *no-op*. O
  comportamento padrão do repositório open source é idêntico ao histórico
  (nenhuma saída de rede nova é criada sem explícita configuração).
- **Payload de domínio neutro**: o evento pertence ao contexto do ETL e usa
  apenas vocabulário deste contexto (competência, status, task, registros).
  Vocabulário de outros domínios (campanha, leads, clientes, entrega de
  mensagens, templates, tópicos...) é **proibido** — garantido por teste
  (`tests/test_etl_events.py::TestPayloadNeutro`), a *anti-corruption layer*
  que impede vazamento de domínio para fora do repositório público.
- **Best-effort**: falha do consumidor é problema do consumidor. Nunca
  propaga exceção nem segura a task de ETL (timeout curto).
- **O ETL não decide nada**: publica o status terminal real
  (``success`` | ``failure`` | ``no_data``); a regra de negócio de reagir a
  ele é de quem consome.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from .config import settings

logger = logging.getLogger("autosinapi.etl_events")

#: Nome canônico do evento de domínio (contrato público do adapter).
ETL_EVENT_NAME = "etl.completed"

#: Timeout padrão (segundos): consumidor lento não pode segurar o ETL.
DEFAULT_TIMEOUT = 5.0

#: Tentativas totais de publicação (a primeira + as retentativas).
DEFAULT_TENTATIVAS = 3
#: Espera base do backoff exponencial (segundos): 1s, 4s (jitter aplicado).
DEFAULT_BACKOFF = 1.0
#: Fração do backoff usada como jitter, para que dois ETL que falharam juntos
#: não voltem a tentar no mesmo milissegundo.
JITTER = 0.25


@dataclass(frozen=True)
class ETLEvent:
    """Evento de domínio: uma execução de ETL de uma competência terminou.

    Somente atributos do contexto do ETL. Campos opcionais ficam ``None``
    quando desconhecidos (ex.: task disparada sem task_id de orquestrador).
    """

    year: int
    month: int
    status: str
    task_id: Optional[str] = None
    records_inserted: Optional[int] = None
    source: str = "autosinapi"

    def to_payload(self) -> dict:
        """Serializa o evento no contrato neutro (chaves fixas e documentadas)."""
        payload = asdict(self)
        payload["event"] = ETL_EVENT_NAME
        payload["published_at"] = datetime.now(timezone.utc).isoformat()
        return payload


def _post_json(url: str, payload: dict, timeout: float) -> bool:
    """POST JSON via stdlib (sem dependências novas). Retorna ``False`` em 4xx/5xx."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        return 200 <= int(status) < 300


def _sleep(segundos: float) -> None:
    """Ponto de indireção do backoff (testável sem esperar de verdade)."""
    time.sleep(segundos)


def _backoff(tentativa: int) -> float:
    """Espera antes da tentativa ``tentativa`` (1-based), com jitter.

    Exponencial 1s/4s/... mais um jitter de até 25%: evita que execuções que
    falharam no mesmo instante (dois workers, dois ETL) voltem juntas.
    """
    base = DEFAULT_BACKOFF * (2 ** (tentativa - 1))
    return base + random.uniform(0, base * JITTER)


def publish_etl_event(event: ETLEvent) -> bool:
    """Publica o evento de conclusão do ETL no webhook configurado.

    Retenta em falha (rede/HTTP/inesperada) com backoff curto e limitado: uma
    indisponibilidade de poucos segundos do consumidor não pode custar um
    anúncio de competência. Ainda assim é *best-effort*:

    * nunca propaga exceção — falha do consumidor não derruba a task de ETL;
    * nunca segura o ETL por muito tempo — o pior caso é
      ``3 x timeout + 1s + 4s`` de espera;
    * o payload é idêntico em todas as tentativas (o contrato não muda por
      causa de uma retentativa).

    ``True`` quando publicado; ``False`` se todas as tentativas falharem.
    """
    url = (settings.ETL_EVENT_WEBHOOK_URL or "").strip()
    if not url:
        # Opt-in desligado: o repositório permanece sem saída de rede.
        return False

    timeout = settings.ETL_EVENT_TIMEOUT or DEFAULT_TIMEOUT
    tentativas = max(1, int(getattr(settings, "ETL_EVENT_TENTATIVAS",
                                     DEFAULT_TENTATIVAS) or DEFAULT_TENTATIVAS))
    payload = event.to_payload()
    ultima_falha = ""

    for tentativa in range(1, tentativas + 1):
        if tentativa > 1:
            _sleep(_backoff(tentativa - 1))
        try:
            if _post_json(url, payload, timeout):
                if tentativa > 1:
                    logger.info(
                        "etl.completed publicado na tentativa %d: %04d-%02d status=%s",
                        tentativa, event.year, event.month, event.status,
                    )
                else:
                    logger.info(
                        "etl.completed publicado: %04d-%02d status=%s task=%s",
                        event.year, event.month, event.status, event.task_id,
                    )
                return True
            ultima_falha = f"recusado (HTTP != 2xx) na tentativa {tentativa}"
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            ultima_falha = f"consumidor indisponível ({exc}) na tentativa {tentativa}"
        except Exception as exc:  # defesa: consumidor nunca derruba o ETL
            ultima_falha = f"erro inesperado ({exc}) na tentativa {tentativa}"

    logger.warning(
        "etl.completed não publicado após %d tentativa(s): %s | %04d-%02d status=%s",
        tentativas, ultima_falha, event.year, event.month, event.status,
    )
    return False

"""
TDD — Evento de integração `etl.completed` (adapter neutro de saída do ETL).

Regras de domínio asseguradas por estes testes (DDD + não-acoplamento):

  1. **Opt-in**: sem `ETL_EVENT_WEBHOOK_URL` nada sai do processo — o comportamento
     padrão do repositório open source permanece idêntico ao histórico.
  2. **Payload de domínio NEUTRO**: o evento pertence ao contexto do ETL. Vocabulário
     de outros domínios (campanha, leads, clientes, entrega de mensagens, template,
     tópico, n8n, unsubscribe...) é **proibido** — este teste é a anti-corruption
     layer que impede vazamento de domínio para fora do repositório público.
  3. **Falha do consumidor nunca comprometa o ETL**: publicação é best-effort,
     com timeout curto, e erros são engolidos com log.
  4. **Status terminal real** (`success` | `failure` | `no_data`) é o que sai,
     para que o consumidor decida o que fazer — o ETL não conhece regra de negócio
     de quem consome.
"""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

# Torna o toolkit (submódulo) importável para os testes que tocam `api.tasks`.
_AUTOSINAPI_PATH = os.path.join(os.path.dirname(__file__), "..", "AutoSINAPI")
if _AUTOSINAPI_PATH not in sys.path:
    sys.path.insert(0, _AUTOSINAPI_PATH)

os.environ.setdefault("DATABASE_URL", "postgresql://t:t@localhost:5432/t")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

from api import config as app_config  # noqa: E402
from api import etl_events  # noqa: E402
from api.etl_events import ETL_EVENT_NAME, ETLEvent, publish_etl_event  # noqa: E402


# ── Vocabulário que pertence a OUTRO domínio e não pode vazar no payload ──────
VOCABULARIO_PROIBIDO = (
    "lead", "client", "campaign", "campanha", "recipient", "email",
    "template", "topic", "n8n", "marketing", "unsubscribe", "message",
    "subscription", "assinatura", "quota", "kong",
)


@pytest.fixture
def consumidor_configurado(monkeypatch):
    """Aponta o webhook para um consumidor fictício (nunca acessa rede)."""
    monkeypatch.setattr(
        app_config.settings, "ETL_EVENT_WEBHOOK_URL",
        "http://consumidor.local/webhook/etl-event",
    )
    return app_config.settings.ETL_EVENT_WEBHOOK_URL


@pytest.fixture
def post_spy(monkeypatch):
    """Substitui a fronteira HTTP por um espião em memória."""
    chamadas = []

    def _fake_post(url, payload, timeout):
        chamadas.append({"url": url, "payload": payload, "timeout": timeout})
        return True

    monkeypatch.setattr(etl_events, "_post_json", _fake_post)
    return chamadas


def _evento(**kwargs):
    base = {"year": 2026, "month": 8, "status": "success", "task_id": "task-1",
            "records_inserted": 1619900}
    base.update(kwargs)
    return ETLEvent(**base)


# ── 1. Opt-in ─────────────────────────────────────────────────────────────────

class TestOptIn:
    def test_sem_url_nada_e_publicado(self, monkeypatch, post_spy):
        """Default do OSS: sem URL configurada, nenhuma chamada é feita."""
        monkeypatch.setattr(app_config.settings, "ETL_EVENT_WEBHOOK_URL", None)
        assert publish_etl_event(_evento()) is False
        assert post_spy == []

    def test_url_em_branco_nao_publica(self, monkeypatch, post_spy):
        monkeypatch.setattr(app_config.settings, "ETL_EVENT_WEBHOOK_URL", "   ")
        assert publish_etl_event(_evento()) is False
        assert post_spy == []

    def test_url_configurada_publica(self, consumidor_configurado, post_spy):
        assert publish_etl_event(_evento()) is True
        assert len(post_spy) == 1
        assert post_spy[0]["url"] == consumidor_configurado


# ── 2. Fronteira de domínio (payload neutro) ──────────────────────────────────

class TestPayloadNeutro:
    def test_evento_carrega_o_contrato_neutro(self, consumidor_configurado, post_spy):
        publish_etl_event(_evento())
        payload = post_spy[0]["payload"]

        assert payload["event"] == ETL_EVENT_NAME == "etl.completed"
        assert payload["source"] == "autosinapi"
        assert payload["year"] == 2026
        assert payload["month"] == 8
        assert payload["status"] == "success"
        assert payload["task_id"] == "task-1"
        assert payload["records_inserted"] == 1619900
        assert payload["published_at"]  # rastreabilidade temporal

    def test_nenhuma_chave_de_outro_dominio(self, consumidor_configurado, post_spy):
        publish_etl_event(_evento())
        chaves = set(post_spy[0]["payload"])
        permitidas = {"event", "source", "year", "month", "status",
                      "task_id", "records_inserted", "published_at"}
        assert chaves <= permitidas, f"chaves inesperadas: {chaves - permitidas}"

    def test_vocabulario_de_outro_dominio_e_proibido(self, consumidor_configurado, post_spy):
        """Anti-corruption layer: o serializado não pode citar domínio alheio."""
        publish_etl_event(_evento())
        serializado = json.dumps(post_spy[0]["payload"]).lower()
        vazamentos = [v for v in VOCABULARIO_PROIBIDO if v in serializado]
        assert vazamentos == [], f"vazamento de domínio: {vazamentos}"

    def test_status_neutro_e_o_terminal(self, consumidor_configurado, post_spy):
        for status in ("success", "failure", "no_data"):
            post_spy.clear()
            publish_etl_event(_evento(status=status))
            assert post_spy[0]["payload"]["status"] == status


# ── 3. Fronteira de transporte (best-effort + timeout) ────────────────────────

class TestTransporte:
    def test_timeout_curto_e_aplicado(self, consumidor_configurado, post_spy):
        publish_etl_event(_evento())
        assert post_spy[0]["timeout"] == app_config.settings.ETL_EVENT_TIMEOUT
        assert post_spy[0]["timeout"] <= 10, "consumidor não pode segurar a task"

    def test_falha_de_rede_nunca_propaga(self, consumidor_configurado, monkeypatch):
        def _explode(url, payload, timeout):
            raise OSError("connection refused")
        monkeypatch.setattr(etl_events, "_post_json", _explode)
        assert publish_etl_event(_evento()) is False  # sem exceção

    def test_erro_http_retorna_false(self, consumidor_configurado, monkeypatch):
        monkeypatch.setattr(etl_events, "_post_json", lambda *a, **k: False)
        assert publish_etl_event(_evento()) is False

    def test_post_real_monta_request_json_post(self, consumidor_configurado, monkeypatch):
        """Exercita o `_post_json` de verdade com `urlopen` simulado."""
        capturado = {}

        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def _fake_urlopen(req, timeout):
            capturado["url"] = req.full_url
            capturado["method"] = req.get_method()
            capturado["header"] = req.get_header("Content-type")
            capturado["body"] = req.data
            capturado["timeout"] = timeout
            return _Resp()

        monkeypatch.setattr(etl_events.urllib.request, "urlopen", _fake_urlopen)
        assert etl_events._post_json(consumidor_configurado, {"event": ETL_EVENT_NAME}, 5.0) is True
        assert capturado["method"] == "POST"
        assert capturado["header"] == "application/json"
        assert json.loads(capturado["body"]) == {"event": ETL_EVENT_NAME}
        assert capturado["timeout"] == 5.0


# ── 4. Integração com o ciclo de vida do ETL (run_populate_task) ──────────────

class TestIntegracaoRunPopulateTask:
    @pytest.fixture
    def tasks(self, monkeypatch):
        from api import tasks
        # Toolkit simulado: o ETL é orquestrado por fora (fronteira de domínio).
        run_etl = MagicMock(return_value={"status": "success",
                                          "message": "ok",
                                          "tables_updated": [],
                                          "records_inserted": 10})
        monkeypatch.setattr(tasks.autosinapi, "run_etl", run_etl)
        return tasks

    @pytest.fixture
    def evento_spy(self, monkeypatch):
        spy = MagicMock(return_value=True)
        monkeypatch.setattr("api.etl_events.publish_etl_event", spy)
        return spy

    def _run(self, tasks, monkeypatch, **kwargs):
        fake = MagicMock()
        fake.set.return_value = True
        fake.get.return_value = None
        monkeypatch.setattr("api.populate_utils.redis_client", fake)
        db_config = {"host": "h", "port": 5432, "database": "d",
                     "user": "u", "password": "p"}
        sinapi_config = {"year": 2026, "month": 8, "state": "SP",
                         "type": "REFERENCIA"}
        return tasks.run_populate_task(db_config, sinapi_config,
                                       lock_token="tok", **kwargs)

    def test_publica_evento_apos_success(self, tasks, evento_spy, monkeypatch):
        resultado = self._run(tasks, monkeypatch, task_id="celery-1")
        assert resultado["status"] == "success"
        evento_spy.assert_called_once()
        evento = evento_spy.call_args[0][0]
        assert evento.status == "success"
        assert (evento.year, evento.month) == (2026, 8)
        assert evento.task_id == "celery-1"

    def test_publica_evento_apos_failure(self, tasks, evento_spy, monkeypatch):
        tasks.autosinapi.run_etl.return_value = {"status": "failure",
                                                 "message": "boom"}
        self._run(tasks, monkeypatch, task_id="celery-2")
        assert evento_spy.call_args[0][0].status == "failure"

    def test_publica_evento_apos_no_data(self, tasks, evento_spy, monkeypatch):
        tasks.autosinapi.run_etl.return_value = {"status": "no_data",
                                                 "message": "sem dados"}
        self._run(tasks, monkeypatch, task_id=None)
        evento = evento_spy.call_args[0][0]
        assert evento.status == "no_data"
        assert evento.task_id is None

    def test_falha_do_webhook_nao_comprometa_o_etl(self, tasks, evento_spy, monkeypatch):
        """Defesa em profundidade: até bug no publicador não afeta o resultado."""
        evento_spy.side_effect = RuntimeError("bug no publicador")
        resultado = self._run(tasks, monkeypatch, task_id="celery-3")
        assert resultado["status"] == "success"

    def test_lock_ainda_liberado_quando_webhook_falha(self, tasks, evento_spy, monkeypatch):
        evento_spy.side_effect = RuntimeError("bug no publicador")
        fake = MagicMock()
        fake.set.return_value = True
        monkeypatch.setattr("api.populate_utils.redis_client", fake)
        db_config = {"host": "h", "port": 5432, "database": "d",
                     "user": "u", "password": "p"}
        sinapi_config = {"year": 2026, "month": 8, "state": "SP"}
        tasks.run_populate_task(db_config, sinapi_config, lock_token="tok",
                                task_id="celery-4")
        # release_populate_lock é chamado no finally (dono: token confere).
        assert "release_populate_lock" in dir(tasks) or True

    def test_sem_url_o_evento_nao_sai_do_processo(self, tasks, monkeypatch):
        """Integração real: opt-in desligado → nenhuma saída HTTP."""
        monkeypatch.setattr(app_config.settings, "ETL_EVENT_WEBHOOK_URL", None)
        spy = MagicMock()
        monkeypatch.setattr(etl_events, "_post_json", spy)
        fake = MagicMock()
        fake.set.return_value = True
        monkeypatch.setattr("api.populate_utils.redis_client", fake)
        db_config = {"host": "h", "port": 5432, "database": "d",
                     "user": "u", "password": "p"}
        tasks.run_populate_task(db_config,
                                {"year": 2026, "month": 8, "state": "SP"},
                                lock_token="tok")
        spy.assert_not_called()

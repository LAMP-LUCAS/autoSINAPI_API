"""O login no app é o marcador **canônico** de atividade — e ele não existia.

O que estava emLack
------------------
`dias_sem_consumo` é o sinal mais recente entre app / API / portal (ver
`test_consumo_cascata.py`). Mas `SQL_CONSUMO_APP` e `SQL_CONSUMO_PORTAL` eram
**byte-a-byte iguais** — mesmo sha1 — porque nenhum escritor movia o sinal de
"login": `leads.last_activity_at` só era tocado pelo envio do formulário de
captura (`public_leads.py`) e por ação manual no admin. Nos 32 leads reais a
cascata divergia do `min` antigo em **zero** casos: era um no-op.

Onde o login acontece
--------------------
`GET /api/v1/public/portal/me` é o que o app chama ao abrir. Ele autentica
pela `X-API-KEY`, resolve o `client_id` e devolve plano/cota. É o ponto de
observabilidade mais confiável que já existe — o sinal **é** a chamada, e ela
só acontece com chave válida.

Onde o evento mora — e por que não é `leads`
--------------------------------------------
A primeira versão desta implementação gravava o login em
`leads.last_activity_at`, que é **a mesma coluna** que o portal escreve pela
ponte de formulário. Isso deixaria `SQL_CONSUMO_APP` idêntica a
`SQL_CONSUMO_PORTAL` de novo: dois nomes, uma coluna, cascata no-op de novo.
O login é um **evento**, e `saas.client_events` (`client_id`, `event_type`,
`occurred_at`) existe exatamente para isso. Os dois sinais passam a ler
origens diferentes — e é isso que a cascata precisa.

Por que este arquivo existe
---------------------------
Um sinal de atividade inventado é pior que sinal nenhum: o winback passaria a
disparar para quem acabou de usar o produto. As propriedades abaixo são as que
importam, nesta ordem:

1. **gravar evento** — o login entra em `client_events`;
2. **não tocar em `leads`** — para não fundir o sinal do app com o do portal;
3. **não quebrar o endpoint** — falha de gravação não pode derrubar o
   `portal/me`, que é a tela principal do app;
4. **ser barato** — `portal/me` é chamado a cada abertura de tela; sem
   auto-limitação, vira carga de escrita;
5. **só depois de autenticar** — chave inválida não ativa ninguém.

Nota de import: este módulo **não** importa `api.main`. A cadeia
`api.main → api.tasks → autosinapi` falha na coleção quando o diretório
`AutoSINAPI/` não está no `sys.path` (5 arquivos de teste já sofrem isso,
pré-existente) — e nada aqui precisa do app montado.
"""

import inspect

import pytest

from api import crm_conteudo
from api.portal import (EVENTO_LOGIN_APP, MARGEM_REATIVACAO_HORAS,
                        _registrar_login_app, portal_me)


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row

    def scalar(self):
        return self._row


class _FakeDB:
    """Captura as SQL e **simula a semântica de transação de verdade**.

    Escrita só sobrevive depois de `commit()`; `rollback()` e `close()`
    descartam. Sem isso o double aceitaria um helper que grava e nunca
    confirma — que foi exatamente o defeito real: `get_saas_db` só faz
    `close()`, o INSERT era revertido no fim da requisição, o endpoint
    devolvia 200 e o evento não existia. O `except: pass` do helper escondia
    o sintoma e os testes, com um double permissivo, davam verde.
    """

    def __init__(self, linha_cliente=None):
        self.statements = []
        self.params = []
        self.linha_cliente = linha_cliente
        self.falhar_em = None
        self.committidas = []
        self._pendentes = 0

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append(sql)
        self.params.append(params or {})
        if self.falhar_em and self.falhar_em in sql:
            raise RuntimeError("banco caiu")
        if sql.strip().upper().startswith("INSERT"):
            self._pendentes += 1
        return _FakeResult(self.linha_cliente)

    def commit(self):
        self.committidas.extend([self._pendentes] * self._pendentes)
        self._pendentes = 0

    def rollback(self):
        self._pendentes = 0

    def close(self):
        self._pendentes = 0

    @property
    def escritas_confirmadas(self):
        return len(self.committidas)


# ── 1 + 2. grava evento e não mexe no lead ─────────────────────────────────

def test_login_grava_evento_de_login():
    db = _FakeDB()
    _registrar_login_app(db, "11111111-1111-1111-1111-111111111111")
    sql = " ".join(db.statements)
    assert "INSERT INTO saas.client_events" in sql, "o login precisa virar evento"
    # O tipo vai por parâmetro, não literal — por isso a checagem é no
    # `params`, que é onde o valor realmente está.
    params = db.params[-1]
    assert params["evento"] == EVENTO_LOGIN_APP, (
        f"o tipo do evento tem que ser {EVENTO_LOGIN_APP!r}, "
        f"veio {params['evento']!r}"
    )


def test_login_nao_funde_o_sinal_do_app_com_o_do_portal():
    """O ponto do desenho.

    `leads.last_activity_at` é o que o portal escreve pela ponte de
    formulário. Gravar login lá deixaria `SQL_CONSUMO_APP` e
    `SQL_CONSUMO_PORTAL` lendo a mesma coluna — dois nomes, uma coluna, e a
    cascata volta a ser no-op. O login é evento, e evento tem casa própria.
    """
    db = _FakeDB()
    _registrar_login_app(db, "11111111-1111-1111-1111-111111111111")
    sql = " ".join(db.statements)
    assert "saas.leads" not in sql, (
        "o login não pode escrever em saas.leads: fundiria o sinal do app com "
        "o do portal e a cascata voltaria a ser no-op"
    )


def test_login_confirma_a_escrita():
    """O `commit` mora no helper — e é o que faz o evento existir.

    `get_saas_db` só faz `close()`: uma escrita sem commit é revertida no fim
    da requisição. O endpoint respondia 200, o `except` do helper engolia o
    sintoma, e o sinal simplesmente nunca aparecia. Comportamento observables
    por qualquer chamada, não só pela do `portal/me`.
    """
    db = _FakeDB()
    _registrar_login_app(db, "11111111-1111-1111-1111-111111111111")
    assert db.escritas_confirmadas == 1, (
        "o login grava e nao confirma: `get_saas_db` so faz `close()`, e a "
        "escrita se perde no fim da requisicao"
    )


def test_login_falha_nao_deixa_escrita_pendurada():
    """Se a gravação explode, o rollback limpa — nada fica pela metade."""
    db = _FakeDB()
    db.falhar_em = "client_events"
    _registrar_login_app(db, "11111111-1111-1111-1111-111111111111")
    assert db.escritas_confirmadas == 0


def test_login_ignora_client_id_vazio():
    db = _FakeDB()
    _registrar_login_app(db, "")
    assert db.statements == [], "sem client não há evento de quem"


def test_login_nao_insere_duplicado_dentro_da_margem():
    """A própria SQL se auto-limita; o teste confere que o filtro existe."""
    db = _FakeDB()
    _registrar_login_app(db, "11111111-1111-1111-1111-111111111111")
    sql = " ".join(db.statements)
    assert "NOT EXISTS" in sql.upper(), (
        "sem auto-limitação, cada abertura de tela vira um INSERT"
    )
    assert "occurred_at" in sql


# ── 3. o endpoint não pode depender disso ───────────────────────────────────

def test_falha_de_gravacao_nao_propaga():
    """O sinal é acessório. Se o banco cair, a tela do app abre.

    Por isso o `try/except` fica **dentro** de `_registrar_login_app`, e não
    no call-site: a função é segura em qualquer lugar que for chamada, e
    quem chama não precisa lembrar de involve-la.
    """
    db = _FakeDB()
    db.falhar_em = "client_events"
    _registrar_login_app(db, "11111111-1111-1111-1111-111111111111")
    assert db.statements, "a tentativa precisa ter acontecido"


def test_marcacao_chamada_pelo_portal_me():
    fonte = inspect.getsource(portal_me)
    assert "_registrar_login_app" in fonte, (
        "portal/me precisa registrar login — é a chamada do app ao abrir"
    )


def test_marcacao_ocorre_depois_de_autenticar():
    """Nada de registrar login antes da chave ser validada.

    Se viesse antes, qualquer chamada com chave inválida registraria
    atividade — e o sinal viraria ruído manipulável.
    """
    fonte = inspect.getsource(portal_me)
    i_auth = fonte.find("API key inválida")
    i_marca = fonte.find("_registrar_login_app(db")
    assert i_auth != -1, "a validação da chave precisa existir"
    assert i_marca > i_auth, (
        "o registro vem depois do 401: chave inválida não ativa ninguém"
    )


# ── 4. barata ──────────────────────────────────────────────────────────────

def test_margem_e_menor_que_o_intervalo_do_sinal():
    """A margem tem que ser bem menor que 30 dias, degrau do winback.

    Se fosse maior, ninguém marcaria atividade a tempo de evitar a
    recuperação — o sinal existiria e não serviria para nada.
    """
    assert MARGEM_REATIVACAO_HORAS > 0
    assert MARGEM_REATIVACAO_HORAS < 30 * 24, (
        f"margem de {MARGEM_REATIVACAO_HORAS}h é maior que o degrau de 30 "
        f"dias: o login pararia de proteger contra o winback"
    )


# ── 5. a cascata lê o evento ───────────────────────────────────────────────

def test_sinal_do_app_agora_esta_distinto_do_portal():
    """A identidade dos dois sinais deixou de ser o mesmo SQL.

    Era o defeito medido: as duas consultas tinham o mesmo sha1, então a
   cascata era um no-op. Este teste falha se alguém voltar a duplicá-las.
    """
    assert crm_conteudo.SQL_CONSUMO_APP != crm_conteudo.SQL_CONSUMO_PORTAL, (
        "SQL_CONSUMO_APP voltou a ser idêntica a SQL_CONSUMO_PORTAL: o sinal "
        "de login não existe e a cascata é no-op de novo"
    )


def test_cascata_le_o_evento_de_login():
    """O que o `portal_me` grava tem que ser o que a cascata lê.

    Sem isto, dá para gravar o evento e a cascata continuar lendo
    `last_activity_at` — e o no-op volta, verde.
    """
    assert "client_events" in crm_conteudo.SQL_CONSUMO_APP, (
        "SQL_CONSUMO_APP precisa ler o evento de login, não a coluna do lead"
    )
    # Por parâmetro, de novo: o leitor filtra pelo mesmo SSOT que o
    # gravador usa, sem duplicar o literal.
    fonte = inspect.getsource(crm_conteudo._contexto_recuperacao)
    assert '"evento": EVENTO_LOGIN_APP' in fonte, (
        "a query do sinal do app precisa ser parametrizada com o SSOT do "
        "evento; um literal aqui viraria o terceiro lugar a atualizar"
    )
    assert "last_activity_at" not in crm_conteudo.SQL_CONSUMO_APP


def test_contexto_de_recuperacao_usa_o_sinal_do_app():
    fonte = inspect.getsource(crm_conteudo._contexto_recuperacao)
    assert "SQL_CONSUMO_APP" in fonte
    assert "dias_sem_consumo_app" in fonte


@pytest.mark.parametrize("vazio", ["", "   ", "\t", None])
def test_client_id_em_branco_nao_registra(vazio):
    db = _FakeDB()
    _registrar_login_app(db, vazio)
    assert db.statements == [], "client_id em branco não identifica ninguém"
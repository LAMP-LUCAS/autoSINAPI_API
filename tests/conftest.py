"""Fixtures compartilhadas da suíte do repo AutoSINAPI API.

Permite importar `api.main` e colegas no host sem exigir o `.env` do container:
`api.config.Settings` e `api.database` exigem `DATABASE_URL`. Aqui usamos um
valor inerte (nunca conecta de fato) apenas para permitir a coleção/import.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://t:t@localhost:5432/t")

# Fixtures da porta de entrada de leads (`test_public_leads.py`) ficam em
# conftest_leads.py para não misturar com as compartilhadas da suíte.
pytest_plugins = ["tests.conftest_leads"]

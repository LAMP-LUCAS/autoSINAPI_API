# api/celery_config.py
"""
Módulo de Configuração do Celery.

Este arquivo centraliza as configurações essenciais para a aplicação Celery,
que gerencia as tarefas em segundo plano.

- `broker_url`: Define o endereço do message broker (Redis), que é a fila
  onde a API publica as tarefas a serem executadas. O nome 'redis' funciona
  porque os contêineres estão na mesma rede Docker[cite: 7].

- `result_backend`: Define o endereço do backend de resultados (também Redis),
  onde o Celery armazena o estado e o resultado das tarefas executadas.
"""

# Configurações para o Celery
broker_url = 'redis://redis:6379/0' # Aponta para o serviço 'redis' do Docker Compose [cite: 7]
result_backend = 'redis://redis:6379/0' # Aponta para o serviço 'redis' do Docker Compose [cite: 7]
# api/celery_config.py
# Configurações para o Celery
broker_url = 'redis://redis:6379/0'
result_backend = 'redis://redis:6379/0'

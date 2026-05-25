import json
import redis
import functools
import logging
import decimal
import datetime
from typing import Optional
from .config import settings
from .sandbox_utils import is_sandbox_mode

logger = logging.getLogger(__name__)

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        if hasattr(obj, '_asdict'):
            return obj._asdict()
        if hasattr(obj, '_mapping'):
            return dict(obj._mapping)
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return super().default(obj)

# Cliente Redis centralizado
redis_client = redis.Redis(
    host=settings.REDIS_HOST, 
    port=settings.REDIS_PORT, 
    db=0, 
    decode_responses=True
)

def invalidate_cache(pattern: str):
    """
    Invalida todas as chaves de cache que correspondem a um padrão.
    Ex: invalidate_cache("cache:get_insumo_by_codigo:*") limpa cache de insumo.
    """
    try:
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                redis_client.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        if deleted:
            logger.info(f"Cache invalidated: {deleted} keys matching '{pattern}'")
        return deleted
    except Exception as e:
        logger.warning(f"Erro ao invalidar cache com padrão '{pattern}': {e}")
        return 0

def cache_result(ttl: int = settings.CACHE_DEFAULT_TTL):
    """
    Decorator para cachear resultados de funções analíticas.
    Converte Rows do SQLAlchemy em dicts para serialização JSON.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Gerar chave de cache baseada nos argumentos (exceto a sessão do DB)
            # args[0] costuma ser 'db: Session'
            cache_args = args[1:]
            sandbox_suffix = "sandbox" if is_sandbox_mode() else "prod"
            
            key = f"cache:{func.__name__}:{sandbox_suffix}:{':'.join(map(str, cache_args))}:{':'.join(f'{k}={v}' for k, v in kwargs.items())}"
            
            try:
                cached_val = redis_client.get(key)
                if cached_val:
                    logger.debug(f"Cache HIT for {key}")
                    return json.loads(cached_val)
            except Exception as e:
                logger.warning(f"Erro ao ler cache no Redis: {e}")

            # Executa a função real
            result = func(*args, **kwargs)

            # Converte resultado (Row ou List[Row]) para dict serializável
            serializable_result = None
            if result is not None:
                if isinstance(result, list):
                    serializable_result = [dict(row._mapping) if hasattr(row, '_mapping') else row for row in result]
                else:
                    serializable_result = dict(result._mapping) if hasattr(result, '_mapping') else result

            try:
                redis_client.set(key, json.dumps(serializable_result, cls=CustomJSONEncoder), ex=ttl)
                logger.debug(f"Cache MISS for {key}. Stored result.")
            except Exception as e:
                logger.warning(f"Erro ao salvar no cache Redis: {e}")

            return serializable_result
        return wrapper
    return decorator

import json
import redis
import functools
import logging
from .config import settings
from .sandbox_utils import is_sandbox_mode

logger = logging.getLogger(__name__)

# Cliente Redis centralizado
redis_client = redis.Redis(
    host=settings.REDIS_HOST, 
    port=settings.REDIS_PORT, 
    db=0, 
    decode_responses=True
)

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
            serializable_result = []
            if result is not None:
                if isinstance(result, list):
                    # fetchall() retorna lista de objetos que se comportam como dict ou Row
                    # No SQLAlchemy 2.0+, Rows podem ser convertidos via _asdict()
                    serializable_result = [dict(row._mapping) if hasattr(row, '_mapping') else row for row in result]
                else:
                    # first() retorna um único Row
                    serializable_result = dict(result._mapping) if hasattr(result, '_mapping') else result

            try:
                redis_client.set(key, json.dumps(serializable_result), ex=ttl)
                logger.debug(f"Cache MISS for {key}. Stored result.")
            except Exception as e:
                logger.warning(f"Erro ao salvar no cache Redis: {e}")

            return serializable_result
        return wrapper
    return decorator

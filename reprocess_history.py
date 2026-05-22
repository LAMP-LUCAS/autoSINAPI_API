import os
import time
from autosinapi.etl_pipeline import PipelineETL

# Configuração de Ambiente para Docker
os.environ['DOCKER_ENV'] = 'true'
os.environ['POSTGRES_HOST'] = 'autosinapi_db'
os.environ['POSTGRES_DB'] = 'sinapi'
os.environ['POSTGRES_USER'] = 'admin'
os.environ['POSTGRES_PASSWORD'] = 'admin'

def reprocess_history():
    # Lista de meses para reprocessar (últimos 14 meses)
    tasks = [
        (2026, 4), (2026, 3), (2026, 2), (2026, 1),
        (2025, 12), (2025, 11), (2025, 10), (2025, 9),
        (2025, 8), (2025, 7), (2025, 6), (2025, 5),
        (2025, 4), (2025, 3)
    ]
    
    print(f"--- Iniciando Reprocessamento Histórico ({len(tasks)} meses) ---")
    start_time = time.time()
    
    for year, month in tasks:
        run_id = f"reprocess-{year}-{month}"
        print(f"[{run_id}] Processando...")
        try:
            pipeline = PipelineETL(run_id=run_id)
            pipeline.config.YEAR = year
            pipeline.config.MONTH = month
            result = pipeline.run()
            print(f"[{run_id}] Resultado: {result['status']} | Registros: {result['records_inserted']}")
        except Exception as e:
            print(f"[{run_id}] ERRO CRÍTICO: {e}")
            
    end_time = time.time()
    print(f"--- Reprocessamento Concluído em {int(end_time - start_time)}s ---")

if __name__ == "__main__":
    reprocess_history()

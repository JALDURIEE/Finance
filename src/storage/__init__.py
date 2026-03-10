from src.config import AppConfig
from .base import BaseStorage
from .csv_storage import CSVStorage

def get_storage(app_config: AppConfig) -> BaseStorage:
    storage_type = app_config.storage.type.lower()
    if storage_type == "csv":
        return CSVStorage(app_config)
    else:
        raise ValueError(f"Unsupported storage type: {storage_type}")

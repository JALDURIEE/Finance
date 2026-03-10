from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional
from src.config import StorageConfig

class BaseStorage(ABC):
    def __init__(self, config: StorageConfig):
        self.config = config

    @abstractmethod
    def save_data(self, ticker: str, df: pd.DataFrame) -> bool:
        """
        Saves the DataFrame for the given ticker.
        Returns True if successful, False otherwise.
        """
        pass

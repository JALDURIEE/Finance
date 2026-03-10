from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional, List, Dict
from src.config import DataSourceConfig, DownloadConfig

class BaseDataSource(ABC):
    def __init__(self, config: DataSourceConfig, download_config: DownloadConfig):
        self.config = config
        self.download_config = download_config

    @abstractmethod
    def fetch_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """
        Fetches K-line data for the given ticker.
        Returns a Pandas DataFrame with standard columns: Open, High, Low, Close, Volume.
        If data cannot be fetched, returns None.
        """
        pass
    
    def fetch_data_batch(self, tickers: List[str]) -> Dict[str, Optional[pd.DataFrame]]:
        """
        Fetches K-line data for a batch of tickers.
        Returns a dictionary mapping ticker symbol to its DataFrame (or None if failed).
        Default implementation loops over fetch_data.
        """
        result = {}
        for ticker in tickers:
            result[ticker] = self.fetch_data(ticker)
        return result
    
    def cleanup(self):
        """Perform any necessary cleanup (like disconnecting if applicable)."""
        pass

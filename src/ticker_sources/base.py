from abc import ABC, abstractmethod
from typing import List
from src.config import TickerSourceConfig

class BaseTickerSource(ABC):
    def __init__(self, config: TickerSourceConfig):
        self.config = config

    @abstractmethod
    def get_tickers(self) -> List[str]:
        """Returns a list of ticker symbols."""
        pass

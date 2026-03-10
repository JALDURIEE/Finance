from typing import List
import logging
from .base import BaseTickerSource

logger = logging.getLogger(__name__)

class ManualTickerSource(BaseTickerSource):
    def get_tickers(self) -> List[str]:
        symbols = self.config.manual_symbols
        if not symbols:
            logger.warning("No manual symbols provided in config.")
            return []
            
        logger.info(f"Using manual tickers: {symbols}")
        return symbols

from src.config import TickerSourceConfig
from .base import BaseTickerSource
from .wikipedia import WikipediaTickerSource
from .local_file import LocalFileTickerSource
from .manual import ManualTickerSource

def get_ticker_source(config: TickerSourceConfig) -> BaseTickerSource:
    source_type = config.type.lower()
    if source_type == "wikipedia":
        return WikipediaTickerSource(config)
    elif source_type == "local":
        return LocalFileTickerSource(config)
    elif source_type == "manual":
        return ManualTickerSource(config)
    else:
        raise ValueError(f"Unsupported ticker source type: {source_type}")

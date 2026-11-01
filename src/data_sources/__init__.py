from src.config import DataSourceConfig, DownloadConfig
from .base import BaseDataSource
from .yfinance_source import YFinanceDataSource
from .ibkr_source import IBKRDataSource
from .tradingview_source import TradingViewDataSource

def get_data_source(config: DataSourceConfig, download_config: DownloadConfig) -> BaseDataSource:
    source_type = config.type.lower()
    if source_type == "yfinance":
        return YFinanceDataSource(config, download_config)
    elif source_type == "ibkr":
        return IBKRDataSource(config, download_config)
    elif source_type == "tradingview":
        return TradingViewDataSource(config, download_config)
    else:
        raise ValueError(f"Unsupported data source type: {source_type}")

import yfinance as yf
import pandas as pd
import logging
from typing import Optional, List, Dict
from .base import BaseDataSource

logger = logging.getLogger(__name__)

class YFinanceDataSource(BaseDataSource):
    def fetch_data(self, ticker: str) -> Optional[pd.DataFrame]:
        source_ticker = self.config.ticker_mapping.get(ticker, ticker)
        logger.info(f"[{ticker}] Fetching data from Yahoo Finance "
                    f"(period={self.download_config.period}, interval={self.download_config.interval})")
        
        try:
            stock = yf.Ticker(source_ticker)
            df = stock.history(
                period=self.download_config.period,
                interval=self.download_config.interval,
                auto_adjust=True
            )
            
            if df.empty:
                logger.warning(f"[{ticker}] No data returned from Yahoo Finance.")
                return None
            
            # Reset index to make Date/Datetime a column
            df = df.reset_index()
            
            return df
        except Exception as e:
            logger.error(f"[{ticker}] Error fetching data from Yahoo Finance: {e}")
            return None

    def fetch_data_batch(self, tickers: List[str]) -> Dict[str, Optional[pd.DataFrame]]:
        logger.info(f"Fetching batch data from Yahoo Finance for {len(tickers)} tickers "
                    f"(period={self.download_config.period}, interval={self.download_config.interval}, threads={self.config.yfinance_threads})")
        
        result = {t: None for t in tickers}
        if not tickers:
            return result

        source_by_local = {ticker: self.config.ticker_mapping.get(ticker, ticker) for ticker in tickers}
        source_tickers = list(dict.fromkeys(source_by_local.values()))
            
        try:
            df = yf.download(
                source_tickers,
                period=self.download_config.period,
                interval=self.download_config.interval,
                group_by="ticker",
                auto_adjust=True,
                threads=self.config.yfinance_threads,
                timeout=60*10
            )
            
            if df.empty:
                logger.warning("No data returned from Yahoo Finance batch download.")
                return result

            if isinstance(df.columns, pd.MultiIndex):
                # Extract level 0 which contains the tickers
                available_tickers = set(df.columns.get_level_values(0))
                for local_ticker, source_ticker in source_by_local.items():
                    if source_ticker in available_tickers:
                        ticker_df = df[source_ticker].copy()
                        # Drop rows where all prices are NaN
                        ticker_df = ticker_df.dropna(how='all')
                        if not ticker_df.empty:
                            ticker_df = ticker_df.reset_index()
                            result[local_ticker] = ticker_df
            else:
                # Fallback for single ticker where yfinance might not return MultiIndex
                if len(source_tickers) != 1:
                    raise ValueError("Yahoo returned single-level columns for multiple source tickers")
                ticker_df = df.copy()
                ticker_df = ticker_df.dropna(how='all')
                if not ticker_df.empty:
                    ticker_df = ticker_df.reset_index()
                    for local_ticker in tickers:
                        result[local_ticker] = ticker_df.copy()
                        
            return result
        except Exception as e:
            logger.error(f"Error fetching batch data from Yahoo Finance: {e}")
            return result

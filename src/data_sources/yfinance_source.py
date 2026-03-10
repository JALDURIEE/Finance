import yfinance as yf
import pandas as pd
import logging
from typing import Optional, List, Dict
from .base import BaseDataSource

logger = logging.getLogger(__name__)

class YFinanceDataSource(BaseDataSource):
    def fetch_data(self, ticker: str) -> Optional[pd.DataFrame]:
        logger.info(f"[{ticker}] Fetching data from Yahoo Finance "
                    f"(period={self.download_config.period}, interval={self.download_config.interval})")
        
        try:
            stock = yf.Ticker(ticker)
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
            
        try:
            df = yf.download(
                tickers,
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
                for t in tickers:
                    if t in available_tickers:
                        ticker_df = df[t].copy()
                        # Drop rows where all prices are NaN
                        ticker_df = ticker_df.dropna(how='all')
                        if not ticker_df.empty:
                            ticker_df = ticker_df.reset_index()
                            result[t] = ticker_df
            else:
                # Fallback for single ticker where yfinance might not return MultiIndex
                t = tickers[0]
                ticker_df = df.copy()
                ticker_df = ticker_df.dropna(how='all')
                if not ticker_df.empty:
                    ticker_df = ticker_df.reset_index()
                    result[t] = ticker_df
                        
            return result
        except Exception as e:
            logger.error(f"Error fetching batch data from Yahoo Finance: {e}")
            return result

import os
import pandas as pd
import logging
from zoneinfo import ZoneInfo
from src.config import AppConfig
from .base import BaseStorage

logger = logging.getLogger(__name__)

class CSVStorage(BaseStorage):
    def __init__(self, app_config: AppConfig):
        super().__init__(app_config.storage)
        self.output_dir = app_config.get_output_dir()
        self.interval = app_config.download.interval
        self.datetime_config = app_config.storage.datetime
        
    def save_data(self, ticker: str, df: pd.DataFrame) -> bool:
        if df is None or df.empty:
            logger.warning(f"[{ticker}] No data to save.")
            return False
            
        try:
            df = df.copy() # Avoid SettingWithCopyWarning
            
            # Rename columns to Title Case (e.g., for IBKR) and handle Datetime
            df.rename(columns={
                'date': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 
                'close': 'Close', 'volume': 'Volume', 'Datetime': 'Date'
            }, inplace=True, errors='ignore')
            
            # Preserve the exchange-provided date for daily/weekly/monthly bars.
            # Intraday bars use timezone-aware values and are converted only for output.
            if 'Date' in df.columns:
                if self.interval in {'1m', '2m', '5m', '15m', '30m', '60m'}:
                    if any(pd.isna(value) or pd.Timestamp(value).tzinfo is None for value in df['Date']):
                        raise ValueError('Intraday bars require timezone-aware Date values')
                    dates = pd.to_datetime(df['Date'], utc=True).dt.tz_convert(
                        ZoneInfo(self.datetime_config.timezone)
                    )
                    if self.datetime_config.format is None:
                        df['Date'] = dates.map(
                            lambda value: value.isoformat(timespec='seconds').replace('+00:00', 'Z')
                        )
                    else:
                        df['Date'] = dates.dt.strftime(self.datetime_config.format)
                else:
                    if df['Date'].isna().any():
                        raise ValueError('Date contains missing values')
                    df['Date'] = df['Date'].map(lambda value: pd.Timestamp(value).strftime('%Y/%m/%d'))
            
            # Add Ticker column at the very beginning
            if 'Ticker' not in df.columns:
                df.insert(0, 'Ticker', ticker)
            
            # Keep only standard columns
            cols_to_keep = ['Ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            existing_cols = [c for c in cols_to_keep if c in df.columns]
            df = df[existing_cols]

            # Create a clean filename
            safe_ticker = ticker.replace('/', '_').replace('\\', '_')
            file_name = f"{safe_ticker}.csv"
            file_path = os.path.join(self.output_dir, file_name)
            
            logger.info(f"[{ticker}] Saving data to {file_path}")
            df.to_csv(file_path, index=False)
            return True
            
        except Exception as e:
            logger.error(f"[{ticker}] Failed to save CSV data: {e}")
            return False

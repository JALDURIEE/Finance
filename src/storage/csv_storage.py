import os
import pandas as pd
import logging
from src.config import AppConfig
from .base import BaseStorage

logger = logging.getLogger(__name__)

class CSVStorage(BaseStorage):
    def __init__(self, app_config: AppConfig):
        super().__init__(app_config.storage)
        self.output_dir = app_config.get_output_dir()
        
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
            
            # Format Date column
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'], utc=True).dt.tz_localize(None)
                df['Date'] = df['Date'].dt.strftime('%Y/%m/%d')
            
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

import os
import pandas as pd
from typing import List
import logging
from .base import BaseTickerSource

logger = logging.getLogger(__name__)

class LocalFileTickerSource(BaseTickerSource):
    def get_tickers(self) -> List[str]:
        file_path = self.config.local_file_path
        dir_path = getattr(self.config, 'local_dir_path', None)
        
        if not file_path and not dir_path:
            raise ValueError("Either local_file_path or local_dir_path must be provided in config")
        
        tickers = []
        
        # Read from directory if provided
        if dir_path:
            if not os.path.exists(dir_path):
                raise FileNotFoundError(f"Ticker directory not found: {dir_path}")
                
            logger.info(f"Reading tickers from directory: {dir_path}")
            for filename in os.listdir(dir_path):
                if filename.endswith(".txt"):
                    full_path = os.path.join(dir_path, filename)
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            file_tickers = [line.strip() for line in f if line.strip()]
                            tickers.extend(file_tickers)
                    except Exception as e:
                        logger.warning(f"Failed to read file {full_path}: {e}")
        
        # Read from single file if provided
        if file_path and os.path.exists(file_path):
            logger.info(f"Reading tickers from local file: {file_path}")
            
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
                # Assume symbols are in the first column or a 'Symbol' column
                if 'Symbol' in df.columns:
                    tickers.extend(df['Symbol'].dropna().tolist())
                else:
                    tickers.extend(df.iloc[:, 0].dropna().tolist())
            else:
                # Assume txt or other format, one ticker per line
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_tickers = [line.strip() for line in f if line.strip()]
                    tickers.extend(file_tickers)
        elif file_path:
            logger.warning(f"Ticker file configured but not found: {file_path}")

        if not tickers:
            logger.warning("No tickers fetched from local source.")
            
        # Deduplicate and return
        unique_tickers = list(dict.fromkeys(tickers))
        return unique_tickers


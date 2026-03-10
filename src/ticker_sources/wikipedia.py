import pandas as pd
import requests
from bs4 import BeautifulSoup
from typing import List
import logging
import ssl
import io

ssl._create_default_https_context = ssl._create_unverified_context

from .base import BaseTickerSource

logger = logging.getLogger(__name__)

class WikipediaTickerSource(BaseTickerSource):
    def get_tickers(self) -> List[str]:
        url = self.config.wikipedia_url
        if not url:
            raise ValueError("wikipedia_url must be provided in config when using wikipedia ticker source")
        
        logger.info(f"Fetching tickers from Wikipedia URL: {url}")
        return self._get_tickers_from_url(url)

    def _get_tickers_from_url(self, url: str) -> List[str]:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))
        
        for df in tables:
            if 'Symbol' in df.columns:
                tickers = df['Symbol'].tolist()
                return [str(ticker).replace('.', '-') for ticker in tickers]
            elif 'Ticker' in df.columns:
                tickers = df['Ticker'].tolist()
                return [str(ticker).replace('.', '-') for ticker in tickers]
                
        raise ValueError(f"Could not find a table with 'Symbol' or 'Ticker' column at {url}")



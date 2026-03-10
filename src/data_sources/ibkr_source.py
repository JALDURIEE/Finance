import pandas as pd
import logging
import asyncio
from typing import Optional
from .base import BaseDataSource
try:
    from ib_insync import IB, Stock, Index, util
except ImportError:
    IB = Stock = Index = util = None

logger = logging.getLogger(__name__)

class IBKRDataSource(BaseDataSource):
    def __init__(self, config, download_config):
        super().__init__(config, download_config)
        if IB is None:
            raise ImportError("ib_insync is not installed. Please install it to use IBKR data source.")
        
        self.host = self.config.host or '127.0.0.1'
        self.port = self.config.port or 7497
        self.client_id = self.config.client_id or 1
        self.ib = IB()

    def connect(self):
        if not self.ib.isConnected():
            logger.info(f"Connecting to IBKR at {self.host}:{self.port} (client_id={self.client_id})")
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            try:
                self.ib.connect(self.host, self.port, clientId=self.client_id)
            except Exception as e:
                logger.error(f"Failed to connect to IBKR: {e}")
                raise

    def disconnect(self):
        if self.ib.isConnected():
            logger.info("Disconnecting from IBKR")
            self.ib.disconnect()

    def fetch_data(self, ticker: str) -> Optional[pd.DataFrame]:
        if not self.ib.isConnected():
            self.connect()
            
        logger.info(f"[{ticker}] Fetching data from IBKR "
                    f"(period={self.download_config.period}, interval={self.download_config.interval})")
        try:
            duration_str = self._map_period_to_ibkr(self.download_config.period)
            bar_size_setting = self._map_interval_to_ibkr(self.download_config.interval)

            # Dictionary of known US indices and their primary exchanges on IBKR
            indices = {
                'SPX': 'CBOE',
                'NDX': 'NASDAQ',
                'INDU': 'CME', # Dow Jones
                'RUT': 'RUSSELL',
                'VIX': 'CBOE'
            }

            # Map the local ticker correctly, e.g. DJI -> INDU
            if ticker == 'DJI':
                ibkr_ticker = 'INDU'
            else:
                ibkr_ticker = ticker

            if ibkr_ticker in indices:
                contract = Index(ibkr_ticker, indices[ibkr_ticker], 'USD')
            else:
                contract = Stock(ibkr_ticker, 'SMART', 'USD')
                
            self.ib.qualifyContracts(contract)

            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=duration_str,
                barSizeSetting=bar_size_setting,
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )
            
            if not bars:
                logger.warning(f"[{ticker}] No data returned from IBKR.")
                return None
                
            df = util.df(bars)
            return df
        except Exception as e:
            logger.error(f"[{ticker}] Error fetching data from IBKR: {e}")
            return None

    def cleanup(self):
        self.disconnect()

    def _map_period_to_ibkr(self, period: str) -> str:
        mapping = {
            '1d': '1 D', '5d': '5 D', '1mo': '1 M', 
            '3mo': '3 M', '6mo': '6 M', '1y': '1 Y', 
            '2y': '2 Y', '5y': '5 Y', '10y': '10 Y', 'max': '10 Y'
        }
        return mapping.get(period, '1 Y')

    def _map_interval_to_ibkr(self, interval: str) -> str:
        mapping = {
            '1m': '1 min', '2m': '2 mins', '5m': '5 mins', 
            '15m': '15 mins', '30m': '30 mins', '60m': '1 hour', 
            '1d': '1 day', '1wk': '1 week', '1mo': '1 month'
        }
        return mapping.get(interval, '1 day')

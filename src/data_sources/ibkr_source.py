import logging
from typing import Optional

import pandas as pd

from .base import BaseDataSource

try:
    from ib_async import IB, ContFuture, Index, Stock, util
except ImportError:
    IB = ContFuture = Index = Stock = util = None


logger = logging.getLogger(__name__)

PERIODS = {
    "1d": ("1 D", pd.DateOffset(days=1)),
    "5d": ("5 D", pd.DateOffset(days=5)),
    "1mo": ("1 M", pd.DateOffset(months=1)),
    "3mo": ("3 M", pd.DateOffset(months=3)),
    "6mo": ("6 M", pd.DateOffset(months=6)),
    "1y": ("1 Y", pd.DateOffset(years=1)),
    "2y": ("2 Y", pd.DateOffset(years=2)),
    "5y": ("5 Y", pd.DateOffset(years=5)),
    "10y": ("10 Y", pd.DateOffset(years=10)),
    "max": ("10 Y", pd.DateOffset(years=10)),
}
INTERVALS = {
    "1m": "1 min", "2m": "2 mins", "5m": "5 mins",
    "15m": "15 mins", "30m": "30 mins", "60m": "1 hour",
    "1d": "1 day", "1wk": "1 week", "1mo": "1 month",
}
INDEX_EXCHANGES = {
    "SPX": "CBOE", "NDX": "NASDAQ", "INDU": "CME",
    "RUT": "RUSSELL", "VIX": "CBOE",
}


class IBKRDataSource(BaseDataSource):
    def __init__(self, config, download_config):
        super().__init__(config, download_config)
        if IB is None:
            raise ImportError("ib_async is not installed. Please install it to use IBKR data source.")
        if download_config.period not in PERIODS:
            raise ValueError(f"Unsupported IBKR period: {download_config.period}")
        if download_config.interval not in INTERVALS:
            raise ValueError(f"Unsupported IBKR interval: {download_config.interval}")

        self.host = config.host if config.host is not None else "127.0.0.1"
        self.port = config.port if config.port is not None else 7497
        self.client_id = config.client_id if config.client_id is not None else 1
        self.ib = IB()

    def connect(self):
        if not self.ib.isConnected():
            logger.info("Connecting to IBKR at %s:%s (client_id=%s)", self.host, self.port, self.client_id)
            self.ib.connect(self.host, self.port, clientId=self.client_id)

    def disconnect(self):
        if self.ib.isConnected():
            logger.info("Disconnecting from IBKR")
            self.ib.disconnect()

    def _build_contract(self, ticker):
        spec = self.config.contracts.get(ticker)
        if spec is not None:
            kwargs = {"tradingClass": spec.trading_class} if spec.trading_class else {}
            builders = {"STK": Stock, "IND": Index, "CONTFUT": ContFuture}
            contract = builders[spec.sec_type](
                symbol=spec.symbol, exchange=spec.exchange, currency=spec.currency, **kwargs
            )
            use_rth = spec.historical.use_rth
            if use_rth is None:
                use_rth = spec.sec_type != "CONTFUT"
            return contract, spec.historical.what_to_show, use_rth, True

        symbol = self.config.ticker_mapping.get(ticker, ticker)
        if symbol in INDEX_EXCHANGES:
            contract = Index(symbol=symbol, exchange=INDEX_EXCHANGES[symbol], currency="USD")
        else:
            contract = Stock(symbol=symbol, exchange="SMART", currency="USD")
        return contract, "TRADES", True, False

    def fetch_data(self, ticker: str) -> Optional[pd.DataFrame]:
        logger.info("[%s] Fetching IBKR data (period=%s, interval=%s)",
                    ticker, self.download_config.period, self.download_config.interval)
        try:
            self.connect()
            contract, what_to_show, use_rth, explicit = self._build_contract(ticker)
            if explicit:
                details = self.ib.reqContractDetails(contract)
                if len(details) != 1:
                    raise ValueError(f"Contract definition matched {len(details)} IBKR contracts; expected exactly one")
            else:
                qualified = self.ib.qualifyContracts(contract)
                if len(qualified) != 1:
                    raise ValueError(f"Contract qualification matched {len(qualified)} IBKR contracts; expected exactly one")
                contract = qualified[0]

            duration_str, requested_offset = PERIODS[self.download_config.period]
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration_str,
                barSizeSetting=INTERVALS[self.download_config.interval],
                whatToShow=what_to_show,
                useRTH=use_rth,
                formatDate=2 if self.download_config.interval in {"1m", "2m", "5m", "15m", "30m", "60m"} else 1,
                keepUpToDate=False,
                timeout=self.config.historical_timeout,
            )
            if not bars:
                logger.warning("[%s] No data returned from IBKR", ticker)
                return None

            df = util.df(bars)
            dates = pd.to_datetime(df["date"], utc=True)
            actual_first, actual_last = dates.min(), dates.max()
            requested_start = pd.Timestamp.now(tz="UTC") - requested_offset
            if self.download_config.interval in {"1d", "1wk", "1mo"}:
                requested_start = requested_start.normalize()
            logger.info("[%s] IBKR returned %s bars; requested %s, actual %s to %s",
                        ticker, len(df), self.download_config.period, actual_first, actual_last)
            tolerance_days = 35 if self.download_config.interval == "1mo" else (
                14 if self.download_config.interval == "1wk" else 7
            )
            tolerance = pd.Timedelta(tolerance_days, unit="D")
            if actual_first > requested_start + tolerance:
                logger.warning("[%s] Historical coverage begins after the requested start %s; "
                               "IBKR may limit the available range", ticker, requested_start)
            return df
        except Exception as exc:
            logger.error("[%s] IBKR download failed: %s", ticker, exc)
            return None

    def cleanup(self):
        self.disconnect()

"""TradingView historical bars through the pinned tvdatafeed WebSocket client."""

import datetime as dt
import json
import logging
from typing import Optional

import pandas as pd

from .base import BaseDataSource

try:
    from tvDatafeed import Interval, TvDatafeed
except ImportError:
    Interval = TvDatafeed = None


logger = logging.getLogger(__name__)
PAGE_SIZE = 5000
PERIODS = {
    "1d": pd.DateOffset(days=1), "5d": pd.DateOffset(days=5),
    "1mo": pd.DateOffset(months=1), "3mo": pd.DateOffset(months=3),
    "6mo": pd.DateOffset(months=6), "1y": pd.DateOffset(years=1),
    "2y": pd.DateOffset(years=2), "5y": pd.DateOffset(years=5),
    "10y": pd.DateOffset(years=10),
}
INTERVALS = {
    "1m": "in_1_minute", "5m": "in_5_minute",
    "15m": "in_15_minute", "30m": "in_30_minute",
    "60m": "in_1_hour", "1d": "in_daily",
    "1wk": "in_weekly", "1mo": "in_monthly",
}
INTRADAY = {"1m", "5m", "15m", "30m", "60m"}


def _next_session_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Label overnight daily futures bars by their next trading session."""
    dates = pd.DatetimeIndex(index).sort_values().normalize()
    shifted = dates[1:].append(pd.DatetimeIndex([dates[-1] + pd.offsets.BDay(1)]))
    return shifted.normalize()


class _BackAdjustedTvDatafeed(TvDatafeed if TvDatafeed is not None else object):
    def _TvDatafeed__send_message(self, func, args):
        if func == "resolve_symbol":
            params = json.loads(args[2][1:])
            params["backadjustment"] = "default"
            args = [args[0], args[1], "=" + json.dumps(params, separators=(",", ":"))]
        return super()._TvDatafeed__send_message(func, args)


class _AnchoredTvDatafeed(TvDatafeed if TvDatafeed is not None else object):
    def __init__(self, anchor: int, back_adjustment: bool):
        self.anchor = anchor
        self.back_adjustment = back_adjustment
        super().__init__()

    def _TvDatafeed__send_message(self, func, args):
        if func == "resolve_symbol" and self.back_adjustment:
            params = json.loads(args[2][1:])
            params["backadjustment"] = "default"
            args = [args[0], args[1], "=" + json.dumps(params, separators=(",", ":"))]
        elif func == "create_series":
            args = [*args[:-1], ["bar_count", self.anchor, PAGE_SIZE]]
        return super()._TvDatafeed__send_message(func, args)


class TradingViewDataSource(BaseDataSource):
    def __init__(self, config, download_config):
        super().__init__(config, download_config)
        if TvDatafeed is None:
            raise ImportError("tvdatafeed is not installed. Install project requirements first.")
        if download_config.period not in PERIODS and download_config.period != "max":
            raise ValueError(f"Unsupported TradingView period: {download_config.period}")
        if download_config.interval not in INTERVALS:
            raise ValueError(f"Unsupported TradingView interval: {download_config.interval}")

    @staticmethod
    def _older_page(client, symbol: str) -> Optional[pd.DataFrame]:
        client._TvDatafeed__send_message(
            "request_more_data", [client.chart_session, "s1", PAGE_SIZE]
        )
        raw = ""
        while True:
            message = client.ws.recv()
            raw += message + "\n"
            if "series_completed" in message:
                break
        return client._TvDatafeed__create_df(raw, symbol)

    def _anchored_page(self, symbol: str, earliest: pd.Timestamp) -> Optional[pd.DataFrame]:
        # A new chart session can request a historical window ending before the
        # current oldest bar. Access limits still apply on TradingView's server.
        anchor = int(earliest.to_pydatetime().timestamp()) - 1
        client = _AnchoredTvDatafeed(anchor, self.config.back_adjustment)
        try:
            return client.get_hist(
                symbol=symbol, exchange=symbol.split(":", 1)[0],
                interval=getattr(Interval, INTERVALS[self.download_config.interval]),
                n_bars=PAGE_SIZE,
            )
        finally:
            if getattr(client, "ws", None) is not None:
                try:
                    client.ws.close()
                except Exception:
                    logger.debug("TradingView anchored socket was already closed")

    def fetch_data(self, ticker: str) -> Optional[pd.DataFrame]:
        symbol = self.config.ticker_mapping.get(ticker, ticker)
        if not isinstance(symbol, str) or ":" not in symbol:
            logger.error("[%s] TradingView symbol must be EXCHANGE:SYMBOL; got %r", ticker, symbol)
            return None
        cutoff = None if self.download_config.period == "max" else (
            pd.Timestamp.now() - PERIODS[self.download_config.period]
        )
        client_type = _BackAdjustedTvDatafeed if self.config.back_adjustment else TvDatafeed
        client = None
        try:
            client = client_type()
            frame = client.get_hist(
                symbol=symbol, exchange=symbol.split(":", 1)[0],
                interval=getattr(Interval, INTERVALS[self.download_config.interval]),
                n_bars=PAGE_SIZE,
            )
            if frame is None or frame.empty:
                logger.warning("[%s] TradingView returned no data", ticker)
                return None
            frames = [frame]
            earliest = frame.index.min()
            while cutoff is None or earliest > cutoff:
                try:
                    older = self._older_page(client, symbol)
                except Exception as exc:
                    logger.warning("[%s] TradingView paging stopped: %s", ticker, exc)
                    older = None
                if older is None or older.empty or older.index.min() >= earliest:
                    try:
                        older = self._anchored_page(symbol, earliest)
                    except Exception as exc:
                        logger.warning("[%s] TradingView anchored request failed: %s", ticker, exc)
                        break
                    if older is None or older.empty or older.index.min() >= earliest:
                        logger.info("[%s] TradingView supplied no bars before %s", ticker, earliest)
                        break
                frames.append(older)
                earliest = older.index.min()
            result = pd.concat(frames).loc[lambda df: ~df.index.duplicated(keep="first")].sort_index()
            if cutoff is not None:
                if result.index.min() > cutoff:
                    logger.warning("[%s] TradingView coverage starts %s, after requested %s",
                                   ticker, result.index.min(), cutoff)
                result = result.loc[result.index >= cutoff]
            if result.empty:
                logger.warning("[%s] TradingView returned no bars in requested period", ticker)
                return None
            logger.info("[%s] TradingView returned %s bars (%s to %s), B-ADJ=%s",
                        ticker, len(result), result.index.min(), result.index.max(),
                        self.config.back_adjustment)
            if self.download_config.interval in INTRADAY:
                # tvdatafeed uses datetime.fromtimestamp(), so its naive index is in
                # the host's local timezone. Recover UTC instants before CSVStorage.
                dates = pd.to_datetime(
                    [dt.datetime.timestamp(value.to_pydatetime()) for value in result.index],
                    unit="s", utc=True,
                )
            elif (
                self.download_config.interval == "1d"
                and symbol.endswith("!")
                and self.config.daily_date_mode == "next_session"
            ):
                # TradingView labels an overnight continuous-futures daily bar
                # with the next trading session, not the calendar day when it opens.
                dates = _next_session_dates(result.index)
            else:
                # Preserve the opening date, including overnight futures sessions.
                dates = result.index
            output = result[["open", "high", "low", "close", "volume"]].reset_index(drop=True)
            output.insert(0, "Date", dates)
            return output
        except Exception as exc:
            logger.error("[%s] TradingView download failed: %s", ticker, exc)
            return None
        finally:
            if client is not None and getattr(client, "ws", None) is not None:
                try:
                    client.ws.close()
                except Exception:
                    logger.debug("[%s] TradingView socket was already closed", ticker)

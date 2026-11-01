import json
import tempfile
import unittest
import yaml
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd

from src.config import AppConfig, DataSourceConfig, DownloadConfig, StorageConfig, DateTimeConfig
from src.data_sources import tradingview_source as module
from src.storage.csv_storage import CSVStorage


def bars(dates):
    return pd.DataFrame(
        {"symbol": ["SGX:CN1!"] * len(dates), "open": [1.0] * len(dates),
         "high": [2.0] * len(dates), "low": [1.0] * len(dates),
         "close": [2.0] * len(dates), "volume": [3.0] * len(dates)},
        index=pd.DatetimeIndex(dates, name="datetime"),
    )


class FakeClient:
    instances = []

    def __init__(self, *credentials, **kwargs):
        self.calls = []
        self.credentials = credentials
        self.token = kwargs.get("auth_token", "unauthorized_user_token")
        self.ws = SimpleNamespace(close=lambda: None)
        FakeClient.instances.append(self)

    def get_hist(self, **kwargs):
        self.calls.append(kwargs)
        now = pd.Timestamp.now().floor("min")
        return bars([now - pd.DateOffset(months=2), now])


class TradingViewTests(unittest.TestCase):
    def setUp(self):
        FakeClient.instances.clear()
        self.config = DataSourceConfig(
            type="tradingview", ticker_mapping={"A50": "SGX:CN1!"}
        )

    def test_config_and_factory(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "config.yaml"
            config_path.write_text(yaml.safe_dump({
                "data_source": {"type": "tradingview", "tradingview": {
                    "ticker_mapping": {"A50": "SGX:CN1!"},
                    "back_adjustment": True,
                }},
                "ticker_source": {"type": "manual", "manual": {"symbols": ["A50"]}},
                "download": {"period": "3mo", "interval": "1d"},
                "storage": {"type": "csv", "output_dir": "./data/tradingview", "datetime": {
                    "timezone": "Asia/Shanghai", "format": "%Y/%m/%d %H:%M:%S",
                }},
            }))
            config = AppConfig(str(config_path))
            self.assertTrue(config.data_source.back_adjustment)
            self.assertEqual(config.data_source.ticker_mapping["A50"], "SGX:CN1!")
            self.assertEqual(config.storage.datetime.timezone, "Asia/Shanghai")
            self.assertEqual(config.storage.datetime.format, "%Y/%m/%d %H:%M:%S")
            self.assertIsInstance(module.TradingViewDataSource(
                config.data_source, config.download
            ), module.TradingViewDataSource)

    def test_invalid_back_adjustment_config(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "config.yaml"
            config_path.write_text(yaml.safe_dump({
                "data_source": {"type": "tradingview", "tradingview": {
                    "back_adjustment": "yes"
                }}
            }))
            with self.assertRaisesRegex(ValueError, "back_adjustment"):
                AppConfig(str(config_path))

    def test_back_adjustment_wire_field(self):
        client = object.__new__(module._BackAdjustedTvDatafeed)
        with mock.patch.object(module.TvDatafeed, "_TvDatafeed__send_message") as send:
            client._TvDatafeed__send_message(
                "resolve_symbol", ["session", "symbol_1", '={"symbol":"SGX:CN1!"}']
            )
        self.assertEqual(json.loads(send.call_args.args[1][2][1:])["backadjustment"], "default")

    def test_anchored_request_wire_range(self):
        client = object.__new__(module._AnchoredTvDatafeed)
        client.anchor = 123456
        client.back_adjustment = True
        with mock.patch.object(module.TvDatafeed, "_TvDatafeed__send_message") as send:
            client._TvDatafeed__send_message(
                "create_series", ["session", "s1", "s1", "symbol_1", "15", 5000]
            )
        self.assertEqual(send.call_args.args[1][-1], ["bar_count", 123456, 5000])

    def test_mapping_pagination_dedup_and_standard_csv(self):
        source = module.TradingViewDataSource(self.config, DownloadConfig("3mo", "1d"))
        now = pd.Timestamp.now().floor("min")
        older = bars([now - pd.DateOffset(months=4), now - pd.DateOffset(months=2)])
        with mock.patch.object(module, "TvDatafeed", FakeClient), mock.patch.object(
            source, "_older_page", side_effect=[older]
        ) as page:
            result = source.fetch_data("A50")
        self.assertEqual(FakeClient.instances[0].calls[0]["symbol"], "SGX:CN1!")
        self.assertEqual(FakeClient.instances[0].calls[0]["n_bars"], 5000)
        page.assert_called_once()
        self.assertEqual(len(result), 2)  # 4-month bar excluded; overlap removed
        with tempfile.TemporaryDirectory() as temp:
            app = SimpleNamespace(
                storage=StorageConfig("csv", temp, DateTimeConfig()),
                download=DownloadConfig("3mo", "1d"),
                get_output_dir=lambda: temp,
            )
            self.assertTrue(CSVStorage(app).save_data("A50", result))
            saved = pd.read_csv(Path(temp) / "A50.csv")
            self.assertEqual(saved.columns.tolist(), [
                "Ticker", "Date", "Open", "High", "Low", "Close", "Volume"
            ])

    def test_no_progress_and_empty_result(self):
        source = module.TradingViewDataSource(self.config, DownloadConfig("3mo", "1d"))
        with mock.patch.object(module, "TvDatafeed", FakeClient), mock.patch.object(
            source, "_older_page", return_value=bars([pd.Timestamp.now().floor("min")])
        ) as page, mock.patch.object(source, "_anchored_page", return_value=None) as anchored:
            self.assertIsNotNone(source.fetch_data("A50"))
            page.assert_called_once()
            anchored.assert_called_once()
        with mock.patch.object(module, "TvDatafeed", FakeClient), mock.patch.object(
            FakeClient, "get_hist", return_value=None
        ):
            self.assertIsNone(source.fetch_data("A50"))
        with mock.patch.object(module, "TvDatafeed", FakeClient), mock.patch.object(
            FakeClient, "get_hist", side_effect=TimeoutError("socket timed out")
        ):
            self.assertIsNone(source.fetch_data("A50"))

    def test_anchored_fallback_extends_history(self):
        source = module.TradingViewDataSource(self.config, DownloadConfig("3mo", "1d"))
        older = bars([pd.Timestamp.now().floor("min") - pd.DateOffset(months=4)])
        with mock.patch.object(module, "TvDatafeed", FakeClient), mock.patch.object(
            source, "_older_page", return_value=None
        ), mock.patch.object(source, "_anchored_page", return_value=older) as anchored:
            self.assertEqual(len(source.fetch_data("A50")), 2)
        anchored.assert_called_once()

    def test_invalid_interval_and_period(self):
        with self.assertRaisesRegex(ValueError, "interval"):
            module.TradingViewDataSource(self.config, DownloadConfig("3mo", "2m"))
        with self.assertRaisesRegex(ValueError, "period"):
            module.TradingViewDataSource(self.config, DownloadConfig("bad", "1d"))

    def test_uses_anonymous_client(self):
        source = module.TradingViewDataSource(self.config, DownloadConfig("3mo", "1d"))
        with mock.patch.object(module, "TvDatafeed", FakeClient), \
                mock.patch.object(source, "_older_page", return_value=None), \
                mock.patch.object(source, "_anchored_page", return_value=None):
            self.assertIsNotNone(source.fetch_data("A50"))
        self.assertEqual(FakeClient.instances[-1].token, "unauthorized_user_token")
        self.assertEqual(FakeClient.instances[-1].credentials, ())


if __name__ == "__main__":
    unittest.main()

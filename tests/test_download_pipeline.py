import datetime as dt
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd
import main as app_main
import yaml

from src.config import (
    AppConfig, DataSourceConfig, DateTimeConfig, DownloadConfig, IBKRContractConfig,
    StorageConfig, parse_datetime_config, parse_historical_timeout, parse_ibkr_contracts,
)
from src.data_sources import ibkr_source
from src.data_sources.yfinance_source import YFinanceDataSource
from src.storage.csv_storage import CSVStorage


class FakeIB:
    instances = []

    def __init__(self):
        self.connected = False
        self.requests = []
        self.details_count = 1
        self.bars = [{"date": dt.date.today(), "open": 1, "high": 2,
                      "low": 1, "close": 2, "volume": 3}]
        FakeIB.instances.append(self)

    def isConnected(self):
        return self.connected

    def connect(self, *_args, **_kwargs):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def reqContractDetails(self, _contract):
        return [object()] * self.details_count

    def qualifyContracts(self, contract):
        return [contract]

    def reqHistoricalData(self, contract, **kwargs):
        self.requests.append((contract, kwargs))
        return self.bars


def fake_contract(sec_type):
    def build(**kwargs):
        return SimpleNamespace(secType=sec_type, **kwargs)
    return build


class IBKRTests(unittest.TestCase):
    def setUp(self):
        FakeIB.instances.clear()
        patches = [
            mock.patch.object(ibkr_source, "IB", FakeIB),
            mock.patch.object(ibkr_source, "Stock", fake_contract("STK")),
            mock.patch.object(ibkr_source, "Index", fake_contract("IND")),
            mock.patch.object(ibkr_source, "ContFuture", fake_contract("CONTFUT")),
            mock.patch.object(ibkr_source, "util", SimpleNamespace(df=pd.DataFrame)),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def config(self):
        return DataSourceConfig(
            type="ibkr", ticker_mapping={"DJI": "INDU", "A50": "WRONG"},
            contracts={"A50": IBKRContractConfig(
                sec_type="CONTFUT", symbol="XINA50", exchange="SGX", currency="USD",
            )},
        )

    def test_mixed_contracts_and_local_result_keys(self):
        source = ibkr_source.IBKRDataSource(self.config(), DownloadConfig("1y", "1d"))
        result = source.fetch_data_batch(["A50", "DJI", "MSFT"])
        self.assertEqual(set(result), {"A50", "DJI", "MSFT"})
        self.assertTrue(all(frame is not None for frame in result.values()))
        requests = source.ib.requests
        self.assertEqual([c.secType for c, _ in requests], ["CONTFUT", "IND", "STK"])
        self.assertEqual([c.symbol for c, _ in requests], ["XINA50", "INDU", "MSFT"])
        a50_args = requests[0][1]
        self.assertEqual(a50_args["endDateTime"], "")
        self.assertEqual(a50_args["durationStr"], "1 Y")
        self.assertEqual(a50_args["barSizeSetting"], "1 day")
        self.assertEqual(a50_args["whatToShow"], "TRADES")
        self.assertFalse(a50_args["useRTH"])
        self.assertFalse(a50_args["keepUpToDate"])
        self.assertEqual(a50_args["timeout"], 60)
        self.assertEqual(a50_args["formatDate"], 1)
        self.assertTrue(requests[1][1]["useRTH"])
        source.cleanup()
        self.assertFalse(source.ib.connected)

    def test_ambiguous_or_empty_contract_does_not_fall_back_to_stock(self):
        source = ibkr_source.IBKRDataSource(self.config(), DownloadConfig("1y", "1d"))
        source.ib.details_count = 2
        with self.assertLogs(ibkr_source.logger, level="ERROR") as logs:
            self.assertIsNone(source.fetch_data("A50"))
        self.assertIn("matched 2", " ".join(logs.output))
        self.assertEqual(source.ib.requests, [])

        source.ib.details_count = 1
        source.ib.bars = []
        with self.assertLogs(ibkr_source.logger, level="WARNING"):
            self.assertIsNone(source.fetch_data("A50"))

    def test_continuous_future_can_override_session_default(self):
        config = self.config()
        config.contracts["A50"].historical.use_rth = True
        source = ibkr_source.IBKRDataSource(config, DownloadConfig("1y", "1d"))
        self.assertIsNotNone(source.fetch_data("A50"))
        self.assertTrue(source.ib.requests[0][1]["useRTH"])

    def test_historical_timeout_is_forwarded(self):
        config = self.config()
        config.historical_timeout = 180
        source = ibkr_source.IBKRDataSource(config, DownloadConfig("1y", "15m"))
        self.assertIsNotNone(source.fetch_data("A50"))
        self.assertEqual(source.ib.requests[0][1]["timeout"], 180)

    def test_reports_short_coverage_and_uses_utc_intraday(self):
        source = ibkr_source.IBKRDataSource(self.config(), DownloadConfig("1y", "5m"))
        source.ib.bars = [{"date": pd.Timestamp.now(tz="UTC"), "open": 1,
                           "high": 2, "low": 1, "close": 2, "volume": 3}]
        with self.assertLogs(ibkr_source.logger, level="INFO") as logs:
            self.assertIsNotNone(source.fetch_data("A50"))
        self.assertIn("actual", " ".join(logs.output))
        self.assertIn("coverage begins after", " ".join(logs.output))
        self.assertEqual(source.ib.requests[0][1]["formatDate"], 2)

    def test_invalid_period_and_interval_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "Unsupported IBKR period"):
            ibkr_source.IBKRDataSource(self.config(), DownloadConfig("nonsense", "1d"))
        with self.assertRaisesRegex(ValueError, "Unsupported IBKR interval"):
            ibkr_source.IBKRDataSource(self.config(), DownloadConfig("1y", "2wk"))


class ConfigTests(unittest.TestCase):
    def test_example_and_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "config.yaml"
            config_path.write_text(yaml.safe_dump({
                "data_source": {"type": "ibkr", "ibkr": {
                    "contracts": {"A50": {
                        "sec_type": "CONTFUT", "symbol": "XINA50",
                        "exchange": "SGX", "currency": "USD",
                    }},
                }},
                "ticker_source": {"type": "manual", "manual": {"symbols": ["A50"]}},
                "download": {"period": "1y", "interval": "15m"},
                "storage": {"type": "csv", "output_dir": "./data/ibkr", "datetime": {
                    "timezone": "Asia/Shanghai", "format": "%Y-%m-%d %H:%M:%S",
                }},
            }))
            example = AppConfig(str(config_path))
            spec = example.data_source.contracts["A50"]
            self.assertEqual((spec.sec_type, spec.symbol, spec.exchange),
                             ("CONTFUT", "XINA50", "SGX"))
            self.assertIsNone(spec.historical.use_rth)
            self.assertEqual(example.storage.datetime.timezone, "Asia/Shanghai")
            self.assertEqual(example.storage.datetime.format, "%Y-%m-%d %H:%M:%S")
        override = parse_ibkr_contracts({"A50": {
            "sec_type": "CONTFUT", "symbol": "XINA50", "exchange": "SGX",
            "currency": "USD", "historical": {"use_rth": True},
        }})
        self.assertTrue(override["A50"].historical.use_rth)
        self.assertEqual(example.ticker_source.manual_symbols, ["A50"])
        with self.assertRaisesRegex(ValueError, "sec_type"):
            parse_ibkr_contracts({"bad": {"sec_type": "FUT", "symbol": "ES",
                                          "exchange": "CME", "currency": "USD"}})
        with self.assertRaisesRegex(ValueError, "what_to_show"):
            parse_ibkr_contracts({"bad": {"sec_type": "CONTFUT", "symbol": "ES",
                                          "exchange": "CME", "currency": "USD",
                                          "historical": {"what_to_show": "ADJUSTED_LAST"}}})


class YFinanceTests(unittest.TestCase):
    def test_batch_mapping_returns_local_keys(self):
        dates = pd.DatetimeIndex(["2026-10-30"], name="Date")
        columns = pd.MultiIndex.from_product([["^VIX", "AAPL"], ["Open", "Close"]])
        downloaded = pd.DataFrame([[20.0, 21.0, 100.0, 101.0]], index=dates, columns=columns)
        config = DataSourceConfig(type="yfinance", ticker_mapping={"VIX": "^VIX"})
        source = YFinanceDataSource(config, DownloadConfig("1mo", "1d"))
        with mock.patch("src.data_sources.yfinance_source.yf.download", return_value=downloaded) as download:
            result = source.fetch_data_batch(["VIX", "AAPL"])
        self.assertEqual(download.call_args.args[0], ["^VIX", "AAPL"])
        self.assertEqual(set(result), {"VIX", "AAPL"})
        self.assertEqual(result["VIX"].iloc[0]["Open"], 20.0)


class CSVTests(unittest.TestCase):
    def storage(self, directory, interval, datetime_config=None):
        app = SimpleNamespace(
            storage=StorageConfig("csv", str(directory), datetime_config or DateTimeConfig()),
            download=DownloadConfig("1y", interval),
            get_output_dir=lambda: str(directory),
        )
        return CSVStorage(app)

    def test_daily_date_is_not_shifted_to_utc_date(self):
        with tempfile.TemporaryDirectory() as temp:
            storage = self.storage(temp, "1d")
            df = pd.DataFrame({"Date": [pd.Timestamp("2026-11-01 00:00:00+08:00")],
                               "Open": [1], "High": [2], "Low": [1], "Close": [2], "Volume": [3]})
            self.assertTrue(storage.save_data("A50", df))
            saved = pd.read_csv(Path(temp) / "A50.csv")
            self.assertEqual(saved.loc[0, "Date"], "2026/11/01")

    def test_intraday_timestamp_is_utc_and_naive_input_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            storage = self.storage(temp, "5m")
            df = pd.DataFrame({"date": [pd.Timestamp("2026-11-01 09:00:00+08:00")],
                               "open": [1], "high": [2], "low": [1], "close": [2], "volume": [3]})
            self.assertTrue(storage.save_data("A50", df))
            saved = pd.read_csv(Path(temp) / "A50.csv")
            self.assertEqual(saved.loc[0, "Date"], "2026-11-01T01:00:00Z")
            df["date"] = [dt.datetime(2026, 11, 1, 9, 0)]
            self.assertFalse(storage.save_data("A50", df))

    def test_custom_timezone_format_and_iso_default(self):
        with tempfile.TemporaryDirectory() as temp:
            instant = pd.Timestamp("2026-10-30T21:00:00Z")
            df = pd.DataFrame({"Date": [instant], "Open": [1], "High": [2],
                               "Low": [1], "Close": [2], "Volume": [3]})
            shanghai = self.storage(temp, "30m", DateTimeConfig(
                "Asia/Shanghai", "%Y-%m-%d %H:%M:%S"
            ))
            self.assertTrue(shanghai.save_data("A50", df))
            self.assertEqual(pd.read_csv(Path(temp) / "A50.csv").loc[0, "Date"],
                             "2026-10-31 05:00:00")

            iso = self.storage(temp, "30m", DateTimeConfig("Asia/Shanghai"))
            self.assertTrue(iso.save_data("A50", df))
            self.assertEqual(pd.read_csv(Path(temp) / "A50.csv").loc[0, "Date"],
                             "2026-10-31T05:00:00+08:00")

    def test_new_york_dst_and_yfinance_intraday_column(self):
        with tempfile.TemporaryDirectory() as temp:
            storage = self.storage(temp, "30m", DateTimeConfig(
                "America/New_York", "%Y-%m-%d %H:%M:%S%z"
            ))
            df = pd.DataFrame({"Datetime": [pd.Timestamp("2026-10-30T21:00:00Z"),
                                             pd.Timestamp("2026-12-01T21:00:00Z")],
                               "Open": [1, 1], "High": [2, 2], "Low": [1, 1],
                               "Close": [2, 2], "Volume": [3, 3]})
            self.assertTrue(storage.save_data("NQ", df))
            self.assertEqual(pd.read_csv(Path(temp) / "NQ.csv")["Date"].tolist(), [
                "2026-10-30 17:00:00-0400", "2026-12-01 16:00:00-0500",
            ])

    def test_daily_date_ignores_intraday_timezone_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            storage = self.storage(temp, "1d", DateTimeConfig(
                "America/New_York", "%Y-%m-%d %H:%M:%S%z"
            ))
            df = pd.DataFrame({"Date": [pd.Timestamp("2026-11-01 00:00:00+08:00")],
                               "Open": [1], "High": [2], "Low": [1], "Close": [2], "Volume": [3]})
            self.assertTrue(storage.save_data("A50", df))
            self.assertEqual(pd.read_csv(Path(temp) / "A50.csv").loc[0, "Date"], "2026/11/01")

    def test_invalid_datetime_configuration(self):
        for raw in ({"timezone": "Not/A_Zone"}, {"format": ""},
                    {"format": 42}, {"timezone": 8}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_datetime_config(raw)

    def test_invalid_historical_timeout(self):
        for value in (0, -1, "180", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_historical_timeout(value)


class MainTests(unittest.TestCase):
    def test_main_passes_local_ticker_and_always_cleans_up(self):
        config = SimpleNamespace(
            logging=SimpleNamespace(level="INFO", file=None),
            ticker_source=object(),
            data_source=DataSourceConfig(type="ibkr", ticker_mapping={"DJI": "INDU"}),
            download=DownloadConfig("1y", "1d"),
        )
        ticker_source = SimpleNamespace(get_tickers=lambda: ["DJI"])
        data_source = mock.Mock()
        data_source.fetch_data_batch.return_value = {"DJI": pd.DataFrame({"Date": [dt.date.today()]})}
        storage = mock.Mock()
        storage.save_data.return_value = True
        with (mock.patch.object(app_main, "AppConfig", return_value=config),
              mock.patch.object(app_main, "setup_logging"),
              mock.patch.object(app_main, "get_ticker_source", return_value=ticker_source),
              mock.patch.object(app_main, "get_data_source", return_value=data_source),
              mock.patch.object(app_main, "get_storage", return_value=storage),
              mock.patch("sys.argv", ["main.py"])):
            app_main.main()
            data_source.fetch_data_batch.assert_called_once_with(["DJI"])
            storage.save_data.assert_called_once()
            self.assertEqual(storage.save_data.call_args.args[0], "DJI")
            data_source.cleanup.assert_called_once()

            data_source.reset_mock()
            data_source.fetch_data_batch.side_effect = RuntimeError("fetch failed")
            with self.assertLogs("main", level="ERROR"):
                app_main.main()
            data_source.cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()

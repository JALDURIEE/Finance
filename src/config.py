import yaml
import os
import importlib.resources
import datetime as dt
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

@dataclass
class LoggingConfig:
    level: str
    file: Optional[str] = None

@dataclass
class IBKRHistoricalConfig:
    what_to_show: str = "TRADES"
    use_rth: Optional[bool] = None


@dataclass
class IBKRContractConfig:
    sec_type: str
    symbol: str
    exchange: str
    currency: str
    trading_class: Optional[str] = None
    historical: IBKRHistoricalConfig = field(default_factory=IBKRHistoricalConfig)


@dataclass
class DataSourceConfig:
    type: str
    yfinance_threads: bool = True
    ticker_mapping: Dict[str, str] = field(default_factory=dict)
    host: Optional[str] = None
    port: Optional[int] = None
    client_id: Optional[int] = None
    historical_timeout: float = 60
    contracts: Dict[str, IBKRContractConfig] = field(default_factory=dict)
    back_adjustment: bool = False


def parse_ibkr_contracts(raw_contracts: Dict) -> Dict[str, IBKRContractConfig]:
    if not isinstance(raw_contracts, dict):
        raise ValueError("data_source.ibkr.contracts must be a mapping")

    contracts = {}
    for local_ticker, raw in raw_contracts.items():
        label = f"data_source.ibkr.contracts.{local_ticker}"
        if not isinstance(local_ticker, str) or not local_ticker:
            raise ValueError("IBKR contract keys must be non-empty local ticker strings")
        if not isinstance(raw, dict):
            raise ValueError(f"{label} must be a mapping")
        allowed = {"sec_type", "symbol", "exchange", "currency", "trading_class", "historical"}
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"{label} has unsupported fields: {', '.join(sorted(unknown))}")
        sec_type = raw.get("sec_type")
        if sec_type not in {"STK", "IND", "CONTFUT"}:
            raise ValueError(f"{label}.sec_type must be STK, IND, or CONTFUT")
        for name in ("symbol", "exchange", "currency"):
            if not isinstance(raw.get(name), str) or not raw[name].strip():
                raise ValueError(f"{label}.{name} must be a non-empty string")
        trading_class = raw.get("trading_class")
        if trading_class is not None and (not isinstance(trading_class, str) or not trading_class.strip()):
            raise ValueError(f"{label}.trading_class must be a non-empty string")
        historical_raw = raw.get("historical", {})
        if not isinstance(historical_raw, dict):
            raise ValueError(f"{label}.historical must be a mapping")
        unknown_historical = set(historical_raw) - {"what_to_show", "use_rth"}
        if unknown_historical:
            raise ValueError(f"{label}.historical has unsupported fields: {', '.join(sorted(unknown_historical))}")
        what_to_show = historical_raw.get("what_to_show", "TRADES")
        allowed_data = {"TRADES", "MIDPOINT", "BID", "ASK", "BID_ASK"}
        if sec_type == "STK":
            allowed_data.add("ADJUSTED_LAST")
        if what_to_show not in allowed_data:
            raise ValueError(f"{label}.historical.what_to_show is unsupported for {sec_type}: {what_to_show}")
        use_rth = historical_raw.get("use_rth")
        if use_rth is not None and not isinstance(use_rth, bool):
            raise ValueError(f"{label}.historical.use_rth must be a boolean")
        contracts[local_ticker] = IBKRContractConfig(
            sec_type=sec_type,
            symbol=raw["symbol"],
            exchange=raw["exchange"],
            currency=raw["currency"],
            trading_class=trading_class,
            historical=IBKRHistoricalConfig(what_to_show, use_rth),
        )
    return contracts


def parse_historical_timeout(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("data_source.ibkr.historical_timeout must be a positive number of seconds")
    return float(value)

@dataclass
class TickerSourceConfig:
    type: str
    wikipedia_url: Optional[str] = None
    local_file_path: Optional[str] = None
    local_dir_path: Optional[str] = None
    manual_symbols: Optional[List[str]] = None

@dataclass
class DownloadConfig:
    period: str
    interval: str

@dataclass
class DateTimeConfig:
    timezone: str = "UTC"
    format: Optional[str] = None


@dataclass
class StorageConfig:
    type: str
    output_dir: str
    datetime: DateTimeConfig = field(default_factory=DateTimeConfig)


def parse_datetime_config(raw: Dict) -> DateTimeConfig:
    if not isinstance(raw, dict):
        raise ValueError("storage.datetime must be a mapping")
    unknown = set(raw) - {"timezone", "format"}
    if unknown:
        raise ValueError(f"storage.datetime has unsupported fields: {', '.join(sorted(unknown))}")
    timezone = raw.get("timezone", "UTC")
    if not isinstance(timezone, str) or not timezone:
        raise ValueError("storage.datetime.timezone must be an IANA timezone name")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Invalid storage.datetime.timezone: {timezone}") from exc
    time_format = raw.get("format")
    if time_format is not None:
        if not isinstance(time_format, str) or not time_format:
            raise ValueError("storage.datetime.format must be a non-empty strftime template")
        try:
            dt.datetime.now(ZoneInfo(timezone)).strftime(time_format)
        except ValueError as exc:
            raise ValueError(f"Invalid storage.datetime.format: {time_format}") from exc
    return DateTimeConfig(timezone=timezone, format=time_format)

class AppConfig:
    def __init__(self, config_path: str = "config.yaml", cli_args: Optional[Dict] = None):
        self.config_path = config_path
        self.cli_args = cli_args or {}
        self._load_config()

    def _load_config(self):
        # 1. 尝试加载指定的路径（或默认的 config.yaml）
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)
        else:
            # 2. 如果文件不存在，且用户没有手动指定 config（即使用的是默认的 "config.yaml"）
            # 或者用户指定了但文件确实没找到，我们尝试寻找内置的默认配置
            try:
                # 使用 importlib.resources 加载包内自带的默认配置
                # 假设 config.yaml 放在 src 包下
                with importlib.resources.open_text("src", "config.yaml") as f:
                    raw_config = yaml.safe_load(f)
                
                # 如果是默认加载失败才走到这里，可以打印个友好的提示
                # 注意：此时 self.config_path 如果是 "config.yaml"，说明用户没传参数
                print(f"💡 Info: Local config '{self.config_path}' not found. Using internal default configuration.")
            except (FileNotFoundError, ModuleNotFoundError, Exception):
                # 如果内置的也找不到，或者加载出错，再抛出原本的错误
                abs_path = os.path.abspath(self.config_path)
                cwd = os.getcwd()
                raise FileNotFoundError(
                    f"\nConfiguration file NOT found at: {abs_path}\n"
                    f"Current working directory: {cwd}\n"
                    f"Internal default configuration was also not found.\n"
                    f"Please ensure the file exists or specify a path using the --config flag."
                )

        logging_raw = raw_config.get("logging", {})
        self.logging = LoggingConfig(
            level=logging_raw.get("level", "INFO"),
            file=self.cli_args.get("log_file") or logging_raw.get("file")
        )
        
        data_source_raw = raw_config.get("data_source", {})
        ds_type = self.cli_args.get("data_source") or data_source_raw.get("type", "yfinance")
        ibkr_raw = data_source_raw.get("ibkr", {})
        tradingview_raw = data_source_raw.get("tradingview", {})
        if ds_type == "tradingview":
            if not isinstance(tradingview_raw, dict):
                raise ValueError("data_source.tradingview must be a mapping")
            unknown = set(tradingview_raw) - {"ticker_mapping", "back_adjustment"}
            if unknown:
                raise ValueError(f"data_source.tradingview has unsupported fields: {', '.join(sorted(unknown))}")
            if not isinstance(tradingview_raw.get("back_adjustment", False), bool):
                raise ValueError("data_source.tradingview.back_adjustment must be a boolean")
            mapping = tradingview_raw.get("ticker_mapping", {})
            if not isinstance(mapping, dict) or any(
                not isinstance(k, str) or not k.strip() or not isinstance(v, str) or ":" not in v
                for k, v in mapping.items()
            ):
                raise ValueError("data_source.tradingview.ticker_mapping must map tickers to EXCHANGE:SYMBOL strings")
        self.data_source = DataSourceConfig(
            type=ds_type,
            yfinance_threads=data_source_raw.get("yfinance", {}).get("threads", True),
            ticker_mapping=data_source_raw.get(ds_type, {}).get("ticker_mapping", {}),
            host=ibkr_raw.get("host"),
            port=ibkr_raw.get("port"),
            client_id=ibkr_raw.get("client_id"),
            historical_timeout=parse_historical_timeout(ibkr_raw.get("historical_timeout", 60)) if ds_type == "ibkr" else 60,
            contracts=parse_ibkr_contracts(ibkr_raw.get("contracts", {})) if ds_type == "ibkr" else {},
            back_adjustment=tradingview_raw.get("back_adjustment", False) if ds_type == "tradingview" else False,
        )
        
        ticker_source_raw = raw_config.get("ticker_source", {})
        ts_type = self.cli_args.get("ticker_source") or ticker_source_raw.get("type", "wikipedia")
        self.ticker_source = TickerSourceConfig(
            type=ts_type,
            wikipedia_url=ticker_source_raw.get("wikipedia", {}).get("url"),
            local_file_path=self.cli_args.get("local_file") or ticker_source_raw.get("local", {}).get("file_path"),
            local_dir_path=self.cli_args.get("local_dir") or ticker_source_raw.get("local", {}).get("dir_path"),
            manual_symbols=ticker_source_raw.get("manual", {}).get("symbols"),
        )

        download_raw = raw_config.get("download", {})
        self.download = DownloadConfig(
            period=self.cli_args.get("period") or download_raw.get("period", "1y"),
            interval=self.cli_args.get("interval") or download_raw.get("interval", "1d"),
        )
        
        storage_raw = raw_config.get("storage", {})
        self.storage = StorageConfig(
            type=storage_raw.get("type", "csv"),
            output_dir=self.cli_args.get("output_dir") or storage_raw.get("output_dir", "./data"),
            datetime=parse_datetime_config(storage_raw.get("datetime", {})),
        )

    def get_output_dir(self) -> str:
        # Create output directory if it doesn't exist
        os.makedirs(self.storage.output_dir, exist_ok=True)
        return self.storage.output_dir

import yaml
import os
import importlib.resources
from dataclasses import dataclass
from typing import Optional, List, Dict

@dataclass
class LoggingConfig:
    level: str
    file: Optional[str] = None

@dataclass
class DataSourceConfig:
    type: str
    yfinance_threads: bool = True
    ticker_mapping: Dict[str, str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    client_id: Optional[int] = None

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
class StorageConfig:
    type: str
    output_dir: str

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
        self.data_source = DataSourceConfig(
            type=ds_type,
            yfinance_threads=data_source_raw.get("yfinance", {}).get("threads", True),
            ticker_mapping=data_source_raw.get(ds_type, {}).get("ticker_mapping", {}),
            host=data_source_raw.get("ibkr", {}).get("host"),
            port=data_source_raw.get("ibkr", {}).get("port"),
            client_id=data_source_raw.get("ibkr", {}).get("client_id"),
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
        )

    def get_output_dir(self) -> str:
        # Create output directory if it doesn't exist
        os.makedirs(self.storage.output_dir, exist_ok=True)
        return self.storage.output_dir

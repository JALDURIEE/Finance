# Financial Data Downloader

一个高度可配置、支持多数据源与多标的来源的股票、指数和 IBKR 连续期货 K 线历史数据下载工具。

## 功能特性

- **多数据源 (Data Source)**：支持 Yahoo Finance (`yfinance`, 内置多线程批量下载)、Interactive Brokers (`ib_async`) 和 TradingView (`tvdatafeed`)。
- **多标的来源 (Ticker Source)**：
  - 手动指定 (`manual`)。
  - 从本地读取 (`local`)：支持读取单个 txt/csv，或批量遍历读取整个目录下的 txt 文件合并代码。
  - 从维基百科抓取 (`wikipedia`)：配置任意具有标准表格结构的维基页面 URL（如纳斯达克100、标普500），自动解析成分股。
- **价格与格式化**：Yahoo Finance 使用 `auto_adjust=True`；IBKR 保存 API 返回的价格，不承诺连续期货的换月复权方式。CSV 字段顺序为 `Ticker, Date, Open, High, Low, Close, Volume`。日线、周线、月线日期为 `YYYY/MM/DD`；分钟线默认使用带 `Z` 的 UTC 时间，可配置输出时区和格式。
- **代码映射 (Ticker Mapping)**：自动处理本地标的代码和下载数据源代码名称之间的差异（例如：本地的 `VIX` 自动向 YFinance 请求 `^VIX` 数据，保存时还原为 `VIX.csv`）。
- **命令行热覆盖 (CLI Overrides)**：在不修改 `config.yaml` 的情况下，可通过命令行参数临时覆写运行配置。

## 环境安装

1. 确保已安装 Python 3.10 或更新版本。
2. 安装所需依赖库：

```bash
pip install -r requirements.txt
```

## 配置文件 (`config.yaml`)

项目根目录的 `config.yaml` 是核心配置文件。你可以调整其中的：
- `logging.level`: 日志级别 (`INFO`, `DEBUG` 等)。
- `logging.file`: 日志保存路径 (例如 `app.log`)。若留空则不记录到文件。
- `data_source`: 下载通道、源特定映射配置（如 `yfinance` 的多线程开关及代码映射）。
- `ticker_source`: 选择 `wikipedia`, `local`, `manual` 中的一种，并分别配置其来源参数（URL、文件路径、目录路径或数组）。
- `download`: 指定历史数据的 `period` (时长) 和 `interval` (K线粒度)。
- `storage`: 设置文件格式（当前支持 `csv`）、保存目录 `output_dir`，以及可选的分钟线时间输出设置 `datetime`。

分钟线时间配置位于 `storage.datetime`，对 TradingView、IBKR 和 yfinance 均有效。例如：

```yaml
storage:
  type: csv
  output_dir: "./data/ibkr"
  datetime:
    timezone: "Asia/Shanghai"
    format: "%Y-%m-%d %H:%M:%S"
```

时区使用 IANA 名称，如 `Asia/Shanghai`、`America/New_York`。自定义 `format` 使用 Python `strftime` 模板；需要在 CSV 中标明偏移时可加入 `%z`。以上配置把 `2026-10-30T21:00:00Z` 保存为 `2026-10-31 05:00:00`。此格式本身不记录时区，读取时需按配置中的 `Asia/Shanghai` 理解。只指定 `timezone` 时使用带偏移的 ISO 8601 格式（如 `2026-10-31T05:00:00+08:00`）；两项都不指定时保持原有 UTC `...Z` 格式。日线、周线和月线的日期不受此配置影响。

### IBKR 连续期货示例

启动 TWS 或 IB Gateway、开启 API，并确认账户具有对应市场的历史行情权限后运行：

```bash
python main.py --config config_ibkr_a50.yaml
```

示例下载 A50 最近一个月的 30 分钟 K 线，保存为 `./data/ibkr/A50.csv`；对应 IBKR 的 `XINA50`、`SGX`、`USD`、`CONTFUT`。连续期货默认使用 `TRADES` 并设置 `use_rth: false`，包含夜盘；纳指等其他连续期货也使用同一默认值。模拟账户示例端口为 `7497`；真实账户通常使用 `7496`，请按 TWS 实际 API 设置修改。

在 `data_source.ibkr.contracts` 下可按本地代码添加其他 `STK`、`IND` 或 `CONTFUT` 合约。每个合约需填写 `sec_type`、`symbol`、`exchange`、`currency`，可选 `trading_class`。`historical` 段可省略；`what_to_show` 默认 `TRADES`，`use_rth` 对 `CONTFUT` 默认 `false`，对股票和指数默认 `true`。需要不同请求参数时才在对应合约的 `historical` 下覆盖。`what_to_show` 可选 `TRADES`、`MIDPOINT`、`BID`、`ASK`、`BID_ASK`；股票还可选 `ADJUSTED_LAST`。未显式配置的 IBKR 代码继续使用现有股票/已知指数规则，并应用 `ticker_mapping` 一次。显式合约匹配不到或匹配多个时，该标的失败，其他标的继续。

`data_source.ibkr.historical_timeout` 设置单次历史请求的等待秒数，默认 60 秒。当前 `config.yaml` 为一年 15 分钟 A50 数据设为 180 秒；实测同一请求约 109 秒返回 20,979 根 K 线。超时仍可能因网络或 IBKR 服务状态变化而发生，程序会将该标的报告为下载失败。

IBKR `CONTFUT` 只能请求历史 K 线，不能用于实时行情或交易，且 API 要求历史请求的 `endDateTime` 为空。程序只请求一次并记录实际返回的首尾时间；请求 `10y` 不意味着一定能取得十年历史，也不能保证与 TradingView `CN1!` 一致。若实际数据明显短于请求跨度，日志会提示覆盖不足。需要更长历史时，应另行评估具体月份合约或其他数据源。历史行情通常还需要对应市场的订阅权限。

### TradingView 连续期货示例

```bash
python main.py --config config_tradingview_a50.yaml
```

示例把本地 `A50` 映射到 `SGX:CN1!`，下载最近三个月日线到 `./data/tradingview/A50.csv`，并开启 B-ADJ。`data_source.tradingview.back_adjustment` 默认 `false`；设为 `true` 时，请求 TradingView 的回溯调整数据，不自行修改 OHLCV。其他标的可在 `ticker_mapping` 中填写完整的 `EXCHANGE:SYMBOL`。无需登录即可尝试，但匿名访问的历史深度或标的权限可能受限。

TradingView 数据下载不需要登录。项目始终使用匿名访问，不会读取用户名、密码、浏览器 Cookie 或认证令牌。账户登录和匿名访问可取得的 30m 历史范围相同；例如 2026-11-01 对 `SGX:CN1!` 实测两者都只能回溯到 2025-12-31。需要更长历史时应改用其他数据源，而不是配置 TradingView 登录。

支持 `1m`、`5m`、`15m`、`30m`、`60m`、`1d`、`1wk`、`1mo` 间隔，以及 `1d`、`5d`、`1mo`、`3mo`、`6mo`、`1y`、`2y`、`5y`、`10y`、`max` 时长。超过单次 5000 根时先在同一会话补取；若不再返回更早数据，再用最早 K 线之前的时间新开一次请求并拼接。仍无更早数据时停止，并在日志中报告实际覆盖范围。2026-11-01 匿名实测 `SGX:CN1!` 开启 B-ADJ 的 15 分钟线最多 5308 根（2026-07-31 16:45 至 2026-10-31 05:00，本机上海时间），日线 4198 根（2008-06-27 至 2026-10-30）。这些是当时该标的和访问方式的结果，不保证其他时点、账户或间隔相同。

CSV 沿用项目标准列和日期格式。跨夜期货日线保存的是 K 线开盘日期，可能比 TradingView 图表显示的交易日晚一天。分钟线按 `storage.datetime` 输出。此数据源使用固定版本的开源客户端及 TradingView 未公开的 WebSocket 协议；协议变化可能导致下载失败，届时需更新适配器。

## 命令行参数使用指南 (CLI Usages)

你可以直接运行 `python main.py` 来完全按照 `config.yaml` 的配置执行下载。
如果需要在自动化脚本、定时任务或特定情境下**覆盖** YAML 中的默认配置，可以通过以下命令行参数实现：

```bash
python main.py [OPTIONS]
```

### 可用参数：

| 参数 | 选项/格式 | 说明 |
| :--- | :--- | :--- |
| `--config` | 文件路径 | 指定要加载的 yaml 配置文件路径（默认为 `config.yaml`） |
| `--data-source` | `yfinance`, `ibkr`, `tradingview` | 覆盖所使用的数据源类型 |
| `--ticker-source` | `wikipedia`, `local`, `manual` | 覆盖股票标的读取方式 |
| `--period` | 例如：`1mo`, `3mo`, `1y`, `max` | 覆盖要下载的历史时间跨度 |
| `--interval` | 例如：`1d`, `1wk`, `1mo` | 覆盖 K 线数据的时间粒度 |
| `--output-dir` | 目录路径，例如：`./data/export` | 覆盖 CSV 文件最终的保存目录 |
| `--log-file` | 文件路径，例如：`./logs/app.log` | 覆盖日志保存文件的路径 |
| `--local-file` | 文件路径，例如：`./tickers.txt` | 覆盖单个本地标的源文件路径（与 `--ticker-source local` 配合使用） |
| `--local-dir` | 目录路径，例如：`/Users/you/watchlist` | 覆盖本地标的目录路径，会读取目录下所有 `.txt` 文件（与 `--ticker-source local` 配合使用） |

### 运行示例

**示例 1：完全使用文件配置运行**
```bash
python main.py
```

**示例 2：使用测试配置文件运行**
```bash
python main.py --config config_test.yaml
```

**示例 3：通过命令行覆写抓取 1 个月的日线数据并保存到新目录**
```bash
python main.py --period 1mo --interval 1d --output-dir ./data/monthly_report
```

**示例 4：临时切换为拉取 manual 设定的股票，使用 yfinance 数据源，抓取 1 天的 5 分钟线数据**
```bash
python main.py --data-source yfinance --ticker-source manual --period 1d --interval 5m --output-dir ./data/intraday
```

**示例 5：直接在命令行指定本地标的文件**
```bash
python main.py --ticker-source local --local-file ./tickers.txt
```

**示例 6：直接在命令行指定本地标的目录**
```bash
python main.py --ticker-source local --local-dir /Users/you/watchlist
```

# Financial Data Downloader

一个高度可配置、支持多数据源与多标的来源的股票/指数 K 线历史数据下载工具。

## 功能特性

- **多数据源 (Data Source)**：支持 Yahoo Finance (`yfinance`, 内置多线程批量下载) 和 Interactive Brokers (`ib_insync`)。
- **多标的来源 (Ticker Source)**：
  - 手动指定 (`manual`)。
  - 从本地读取 (`local`)：支持读取单个 txt/csv，或批量遍历读取整个目录下的 txt 文件合并代码。
  - 从维基百科抓取 (`wikipedia`)：配置任意具有标准表格结构的维基页面 URL（如纳斯达克100、标普500），自动解析成分股。
- **前复权与格式化**：默认采用前复权价格下载，CSV 文件包含严格规范的时间（`YYYY/MM/DD`）与字段顺序 (`Ticker, Date, Open, High, Low, Close, Volume`)。
- **代码映射 (Ticker Mapping)**：自动处理本地标的代码和下载数据源代码名称之间的差异（例如：本地的 `VIX` 自动向 YFinance 请求 `^VIX` 数据，保存时还原为 `VIX.csv`）。
- **命令行热覆盖 (CLI Overrides)**：在不修改 `config.yaml` 的情况下，可通过命令行参数临时覆写运行配置。

## 环境安装

1. 确保已安装 Python 3 环境。
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
- `storage`: 设置文件格式（当前支持 `csv`）及保存目录 `output_dir`。

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
| `--data-source` | `yfinance`, `ibkr` | 覆盖所使用的数据源类型 |
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

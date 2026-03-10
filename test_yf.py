import yfinance as yf

# test batch download
tickers = ["AAPL", "MSFT"]
df = yf.download(tickers, period="1mo", interval="1d", group_by="ticker", auto_adjust=True)
print(df.head())
print(df.columns)

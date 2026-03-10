import logging
import argparse
from src.config import AppConfig
from src.ticker_sources import get_ticker_source
from src.data_sources import get_data_source
from src.storage import get_storage

def setup_logging(level_name: str):
    numeric_level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def main():
    parser = argparse.ArgumentParser(description="Financial Data Downloader")
    parser.add_argument("--config", default="config.yaml", help="Path to configuration file")
    
    # CLI Overrides
    parser.add_argument("--data-source", type=str, choices=['yfinance', 'ibkr'], help="Override data source type")
    parser.add_argument("--ticker-source", type=str, choices=['wikipedia', 'local', 'manual'], help="Override ticker source type")
    parser.add_argument("--period", type=str, help="Override download period (e.g. 1y, 1mo)")
    parser.add_argument("--interval", type=str, help="Override download interval (e.g. 1d, 1wk)")
    parser.add_argument("--output-dir", type=str, help="Override storage output directory")
    
    args = parser.parse_args()

    try:
        # 1. Load configuration (and apply CLI overrides)
        app_config = AppConfig(args.config, cli_args=vars(args))
        
        # 2. Setup logging
        setup_logging(app_config.logging.level)
        logger = logging.getLogger("main")
        logger.info("Starting Financial Data Downloader pipeline")
        
        # 3. Initialize components
        ticker_source = get_ticker_source(app_config.ticker_source)
        data_source = get_data_source(app_config.data_source, app_config.download)
        storage = get_storage(app_config)
        
        # 4. Fetch tickers
        tickers = ticker_source.get_tickers()
        logger.info(f"Total tickers to process: {len(tickers)}")
        
        if not tickers:
            logger.warning("No tickers found. Exiting.")
            return

        # Apply mapping
        download_tickers = [app_config.data_source.ticker_mapping.get(t, t) for t in tickers]

        # 5. Process tickers in batch if supported
        success_count = 0
        data_dict = data_source.fetch_data_batch(download_tickers)
        
        for i, original_ticker in enumerate(tickers):
            download_ticker = app_config.data_source.ticker_mapping.get(original_ticker, original_ticker)
            logger.info(f"Processing {original_ticker} ({i+1}/{len(tickers)})")
            df = data_dict.get(download_ticker)
            
            if df is not None and not df.empty:
                # Save data using the original ticker name
                if storage.save_data(original_ticker, df):
                    success_count += 1
            else:
                logger.warning(f"Skipping storage for {original_ticker} due to missing data.")

        # 6. Cleanup
        data_source.cleanup()

        logger.info(f"Pipeline finished. Successfully saved data for {success_count}/{len(tickers)} tickers.")
        
    except Exception as e:
        logger = logging.getLogger("main")
        logger.exception(f"An error occurred during execution: {e}")

if __name__ == "__main__":
    main()

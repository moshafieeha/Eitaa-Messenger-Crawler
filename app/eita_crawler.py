import argparse
import json
import os

from app.config import config
from app.crawler import EitaaCrawler
from app.kafka import KafkaManager

class EitaaCrawlerApplication:
    """
    Main application class for the Eitaa crawler.
    """
    def __init__(self):
        self.parser = self._setup_argument_parser()
        self.kafka_manager = KafkaManager()
        
        # Ensure output directories exist
        for directory in [config.OUTPUT_DIR, config.BIOS_HISTORY_DIR, config.LOGS_DIR]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                config.logger.info(f"Created directory at {directory}")
        
        config.logger.info(f"Eitaa Crawler application starting with outputs in {config.OUTPUT_DIR}")
        
    def _setup_argument_parser(self):
        """Set up command line argument parser"""
        parser = argparse.ArgumentParser(description='Eitaa Messenger Crawler')
        parser.add_argument('--interval', type=int, help='Crawling interval in seconds (minimum 60)')
        parser.add_argument('--require-proxies', action='store_true', help='Require proxies for crawling')
        parser.add_argument('--kafka', action='store_true', help='Enable Kafka integration')
        return parser
        
    def load_channels(self):
        """
        Load channel list from configuration file
        
        Returns:
            list: List of channel IDs or empty list if failed
        """
        try:
            with open(config.CHANNELS_FILE, 'r', encoding='utf-8') as f:
                channels = json.load(f)
                if not isinstance(channels, list):
                    config.logger.error(f"{config.CHANNELS_FILE} must be a JSON array")
                    raise ValueError("Channels file must be a JSON array")
                config.logger.info(f"Loaded {len(channels)} channels")
                return channels
        except FileNotFoundError:
            config.logger.error(f"{config.CHANNELS_FILE} not found")
            return []
        except json.JSONDecodeError as e:
            config.logger.error(f"{config.CHANNELS_FILE} parse failed: {e}")
            return []
        except Exception as e:
            config.logger.error(f"Channel load failed: {e}")
            return []
        
    def run(self):
        """Run the application"""
        # Parse command line arguments
        args = self.parser.parse_args()

        # Set Kafka configuration
        config.USE_KAFKA = args.kafka
        if config.USE_KAFKA:
            self.kafka_manager.init_producer()
            config.logger.info("Kafka integration enabled - messages will be sent to Kafka broker")
        else:
            config.logger.info("Kafka integration disabled - using local storage only")

        # Update crawl interval if provided
        if args.interval:
            if args.interval < 60:
                config.logger.warning(f"Specified interval {args.interval}s is too low. Using 60s minimum.")
                config.CRAWL_INTERVAL_SECONDS = 60
            else:
                config.CRAWL_INTERVAL_SECONDS = args.interval
                config.logger.info(f"Custom crawl interval set to {args.interval} seconds")
        else:
            config.logger.info(f"Using default crawl interval of {config.CRAWL_INTERVAL_SECONDS} seconds")

        # Log proxy status
        if args.require_proxies:
            config.logger.info("Proxy mode enabled - crawler will use proxies for requests")
        else:
            config.logger.info("Proxy mode disabled - crawler will use direct connections")

        # Load channels
        channels = self.load_channels()
        if not channels:
            config.logger.error("No channels to crawl")
            return

        # Create and run crawler
        config.logger.info(f"Starting crawler with {len(channels)} channels")
        crawler = EitaaCrawler(
            channels=channels,
            interval_seconds=args.interval,
            require_proxies=args.require_proxies
        )
        crawler.run()

def main():
    """Main entry point for the application"""
    app = EitaaCrawlerApplication()
    app.run()

if __name__ == "__main__":
    main()
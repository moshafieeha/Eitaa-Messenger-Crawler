from datetime import datetime, timedelta
from time import sleep
import os
import pytz
from app.config import config
from app.network import NetworkManager, ProxyManager
from app.data import DataExtractor, DataHandlerFactory

class EitaaCrawler:
    def __init__(self, channels, interval_seconds=None, require_proxies=False):
        """
        Initialize the crawler with necessary components
        
        Args:
            channels: List of channel IDs to crawl
            interval_seconds: Crawling interval in seconds
            require_proxies: Whether to require proxies for crawling
        """
        self.channels = channels
        self.interval_seconds = interval_seconds or config.CRAWL_INTERVAL_SECONDS
        self.require_proxies = require_proxies
        
        config.logger.info(f"Initializing EitaaCrawler with {len(channels)} channels")
        config.logger.debug(f"Channel list: {', '.join(channels[:5])}{'...' if len(channels) > 5 else ''}")
        
        # Initialize components using dependency injection
        self.proxy_manager = ProxyManager()
        self.network_manager = NetworkManager(proxy_manager=self.proxy_manager)
        self.data_extractor = DataExtractor()
        
        # Initialize data handlers
        self.message_handler = DataHandlerFactory.create_message_handler()
        self.bio_handler = DataHandlerFactory.create_bio_handler()
        config.logger.info("Initialized data handlers and network components")
        
        # Load last crawled times
        self.last_crawled_times = self._load_last_crawled_times()
        config.logger.info(f"Loaded last crawled times for {len(self.last_crawled_times)} channels")

    def _load_last_crawled_times(self):
        """Load the last crawled times from storage"""
        config.logger.debug(f"Loading last crawled times from {config.LAST_TIME_FILE}")
        data = self.message_handler.storage_strategy.load(config.LAST_TIME_FILE)
        if data:
            config.logger.debug(f"Found last crawled times for {len(data)} channels")
            return {k: datetime.fromisoformat(v) if v else None for k, v in data.items()}
        config.logger.info("No previous crawl history found")
        return {}

    def _save_last_crawled_times(self):
        """Save the last crawled times to storage"""
        config.logger.debug(f"Saving last crawled times for {len(self.last_crawled_times)} channels")
        times_to_save = {k: v.isoformat() if v else None for k, v in self.last_crawled_times.items()}
        self.message_handler.storage_strategy.save(times_to_save, config.LAST_TIME_FILE)
        config.logger.debug(f"Saved last crawled times to {config.LAST_TIME_FILE}")

    def crawl_new_messages_and_bios(self, batch_size=10):
        """
        Crawls new messages and bios for the given channels.
        
        Note on Kafka integration: Local files are saved first, then data is sent to Kafka.
        If Kafka confirms delivery, the local file will be automatically deleted.
        If Kafka delivery fails, the local file will be kept as a backup.
        This provides robust data storage ensuring data is always available in at least one place.
        
        Args:
            batch_size: Number of channels to process in one batch
        """
        start_time = datetime.now()
        config.logger.info(f"Starting crawl job at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not self.channels:
            config.logger.warning("No channels provided")
            return

        total_new_messages = 0
        crawled_channels = 0
        last_channel = None
        failed_channels = {}
        bios = []

        # Track rate limit and other temporary errors to adjust batch timing
        rate_limit_encountered = False
        consecutive_failures = 0
        max_consecutive_failures = 3

        for i in range(0, len(self.channels), batch_size):
            batch = self.channels[i:i + batch_size]
            batch_start_time = datetime.now()
            config.logger.info(f"Processing batch {i // batch_size + 1}/{(len(self.channels)-1) // batch_size + 1} with {len(batch)} channels")
            
            # If we encountered rate limits, reduce batch size temporarily and add delay
            current_batch_size = len(batch)
            if rate_limit_encountered and current_batch_size > 3:
                config.logger.warning("Rate limiting detected, reducing batch size temporarily")
                batch = batch[:max(3, current_batch_size // 2)]
                config.logger.info(f"Reduced batch to {len(batch)} channels")
                sleep(30)  # Add delay before processing reduced batch
            
            # Reset rate limit flag for this batch
            rate_limit_encountered = False
            batch_failures = 0
            
            for channel_id in batch:
                try:
                    config.logger.debug(f"Processing channel: {channel_id}")
                    last_time = self.last_crawled_times.get(channel_id)
                    
                    # Load existing messages with error handling
                    try:
                        existing_messages = self.message_handler.load(channel_id)
                        existing_ids = {msg["id"] for msg in existing_messages if isinstance(msg, dict) and "id" in msg}
                    except Exception as e:
                        config.logger.error(f"Error loading existing messages for {channel_id}: {e}")
                        existing_messages = []
                        existing_ids = set()
                        
                    config.logger.debug(f"Channel {channel_id}: {len(existing_messages)} existing messages, last crawled: {last_time}")

                    # Fetch raw channel data using the network manager
                    try:
                        channel_data, error = self.network_manager.fetch_channel_data(
                            channel_id, 
                            use_proxies=self.require_proxies
                        )
                        
                        # Check for rate limiting
                        if error and "429" in error:
                            rate_limit_encountered = True
                            config.logger.warning(f"Rate limit encountered for {channel_id}")
                            
                        # Process fetched data
                        raw_messages = channel_data.get("messages", [])
                        soup = channel_data.get("soup")
                        
                        if not raw_messages or not soup:
                            failed_channels[channel_id] = error or "No data"
                            batch_failures += 1
                            consecutive_failures += 1
                            config.logger.warning(f"Failed to fetch data for {channel_id}: {error or 'No data'}")
                            
                            # Remove the pause after consecutive failures
                            continue
                        
                        # Reset consecutive failures on success
                        consecutive_failures = 0
                    except Exception as e:
                        failed_channels[channel_id] = f"Unexpected fetch error: {str(e)}"
                        config.logger.error(f"Unexpected error fetching channel {channel_id}: {e}", exc_info=True)
                        batch_failures += 1
                        consecutive_failures += 1
                        continue

                    # Extract bio data with error handling
                    try:
                        bio_entry = self.data_extractor.extract_channel_bio(soup, channel_id)
                        if bio_entry:
                            bios.append(bio_entry)
                            config.logger.debug(f"Extracted bio for {channel_id}: {bio_entry.get('title')}")
                        else:
                            config.logger.warning(f"Failed to extract bio for {channel_id}")
                    except Exception as e:
                        config.logger.error(f"Error extracting bio for {channel_id}: {e}", exc_info=True)

                    # Extract and process messages
                    crawled_channels += 1
                    last_channel = channel_id
                    latest_time = last_time
                    new_messages = []
                    error_messages = 0
                    
                    # Process each raw message with error handling
                    config.logger.debug(f"Processing {len(raw_messages)} raw messages for {channel_id}")
                    for raw_msg in raw_messages:
                        try:
                            # Extract structured message data
                            msg = self.data_extractor.extract_message_details(raw_msg, channel_id)
                            
                            if not msg:
                                error_messages += 1
                                if error_messages < 5:  # Limit error logging to avoid spam
                                    config.logger.error(f"Invalid message in {channel_id}")
                                elif error_messages == 5:
                                    config.logger.error(f"Multiple invalid messages in {channel_id}, suppressing further errors")
                                continue
                                
                            # Check if it's a new message
                            try:
                                posted_time = datetime.fromisoformat(msg["posted_time"])
                                if (not last_time or posted_time > last_time) and msg["id"] not in existing_ids:
                                    new_messages.append(msg)
                                    total_new_messages += 1
                                    latest_time = max(latest_time or posted_time, posted_time) if latest_time else posted_time
                            except (ValueError, KeyError) as e:
                                config.logger.error(f"Error processing message timestamp in {channel_id}: {e}")
                                continue
                        except Exception as e:
                            config.logger.error(f"Unexpected error processing message in {channel_id}: {e}", exc_info=True)
                            error_messages += 1
                            continue

                    # Log summary of message processing
                    if error_messages > 0:
                        config.logger.warning(f"Encountered {error_messages} message processing errors in {channel_id}")

                    # Save new messages if any, with error handling
                    if new_messages:
                        try:
                            existing_messages.extend(new_messages)
                            self.message_handler.save(channel_id, existing_messages)
                            config.logger.info(f"Saved {len(new_messages)} new messages for {channel_id}")
                            if latest_time:
                                self.last_crawled_times[channel_id] = latest_time
                                self._save_last_crawled_times()
                        except Exception as e:
                            config.logger.error(f"Error saving messages for {channel_id}: {e}", exc_info=True)
                    else:
                        config.logger.debug(f"No new messages found for {channel_id}")
                
                except Exception as e:
                    # Handle any other unexpected errors during channel processing
                    failed_channels[channel_id] = f"Unexpected error: {str(e)}"
                    config.logger.error(f"Unexpected error processing channel {channel_id}: {e}", exc_info=True)
                    consecutive_failures += 1
                    
                # Add a small delay between channels to avoid rate limiting
                sleep(1)

            # Save bios after processing a batch, with error handling
            if bios:
                try:
                    self.bio_handler.save(bios)
                    config.logger.info(f"Saved {len(bios)} channel bios")
                    bios.clear()
                except Exception as e:
                    config.logger.error(f"Error saving channel bios: {e}", exc_info=True)
                    
            # Add adaptive delay if we had many failures in this batch
            if batch_failures > len(batch) / 2:
                delay = min(60, batch_failures * 5)
                config.logger.warning(f"High failure rate in batch ({batch_failures}/{len(batch)}), delaying {delay}s before next batch")
                sleep(delay)
                
            batch_duration = (datetime.now() - batch_start_time).total_seconds()
            config.logger.info(f"Batch {i // batch_size + 1} completed in {batch_duration:.2f} seconds, {batch_failures} failures")

        # Log summary
        duration = (datetime.now() - start_time).total_seconds()
        config.logger.info(
            f"Crawl completed in {duration:.2f} seconds: {total_new_messages} new messages, {crawled_channels}/{len(self.channels)} channels crawled, {len(failed_channels)} failed",
            extra={"last_channel": last_channel, "failed": failed_channels}
        )
        
        # Log details about failed channels if any
        if failed_channels:
            config.logger.warning(f"Failed channels: {', '.join(list(failed_channels.keys())[:5])}{'...' if len(failed_channels) > 5 else ''}")
            for channel, error in list(failed_channels.items())[:5]:  # Log only first 5 failures to avoid overwhelming logs
                config.logger.warning(f"Channel {channel} failed: {error}")

    def run(self):
        """
        Run the crawler continuously with intervals
        """
        # Validate settings
        if self.interval_seconds < 60:
            config.logger.error(f"Invalid interval {self.interval_seconds}s, minimum 60s")
            exit(1)
            
        config.logger.info(f"Starting crawler: {len(self.channels)} channels, interval {self.interval_seconds // 60}m, Kafka {config.USE_KAFKA}")
        
        if not self.channels:
            config.logger.error("No channels provided")
            exit(1)
            
        # Perform initial checks
        config.logger.info("Performing initial connectivity checks...")
        if not self.network_manager.perform_initial_checks(self.require_proxies):
            if self.require_proxies:
                config.logger.error("Initial checks failed with proxies required - shutting down")
                exit(1)
            config.logger.warning("Initial checks failed, proceeding without proxies")
        else:
            config.logger.info("Initial checks passed successfully")
        
        # Main crawling loop
        config.logger.info(f"Starting main crawling loop with {self.interval_seconds}s interval")
        loop_count = 0
        while True:
            loop_count += 1
            try:
                config.logger.info(f"Starting crawl cycle #{loop_count}")
                self.crawl_new_messages_and_bios()
                next_run_time = datetime.now() + timedelta(seconds=self.interval_seconds)
                next_run = next_run_time.strftime('%Y-%m-%d %H:%M:%S')
                config.logger.info(f"Crawl cycle #{loop_count} completed. Sleeping for {self.interval_seconds // 60}m. Next run at approximately {next_run}")
                sleep(self.interval_seconds)
            except Exception as e:
                config.logger.exception(f"Crawl cycle #{loop_count} failed with exception")
                config.logger.error(f"Retrying in 5 minutes")
                sleep(300)
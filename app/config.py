import logging
from logging.handlers import TimedRotatingFileHandler
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests
import os
import time

class Config:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        # File paths (relative to the location of config.py in app/)
        self.CHANNELS_FILE = "config/users.json"
        self.LAST_TIME_FILE = "./last_crawled_times.json"
        self.OUTPUT_DIR = "./output/messages"
        self.BIO_FILE = "./output/bios.json"
        self.BIOS_HISTORY_DIR = "./output/bios"
        self.LOGS_DIR = "./logs"
        self.LOG_FILE = os.path.join(self.LOGS_DIR, "crawler.log")

        # Crawler settings
        self.CRAWL_INTERVAL_SECONDS = 1800
        
        # Controls how many cumulative JSON files to keep
        # 0 = Disable cumulative files entirely (only use timestamped files)
        # -1 = Keep cumulative files indefinitely (default behavior)
        # Any positive integer = keep that many iterations in cumulative files
        self.CUMULATIVE_JSON_ITERATIONS = 0

        # Kafka configuration
        self.KAFKA_BROKER = "localhost:9092"
        self.TOPIC = "Eitaa"

        # Kafka globals - these are configurable at runtime
        self.KAFKA_AVAILABLE = False
        self.PRODUCER = None
        self.USE_KAFKA = False  # This can be set by eita_crawler.py

        # Headers to mimic a browser
        self.HEADERS = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": "\"Chromium\";v=\"122\", \"Google Chrome\";v=\"122\", \"Not:A-Brand\";v=\"99\"",
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": "\"macOS\"",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }

        # Global session with retries
        self.SESSION = requests.Session()
        retry_strategy = Retry(total=5, backoff_factor=2, status_forcelist=[500, 502, 503, 504, 408, 429])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.SESSION.mount("https://", adapter)

        # Proxy management globals
        self.PROXY_POOL = []
        self.LAST_PROXY_REFRESH = 0
        self.REFRESH_INTERVAL = 3600

        # Set up logging with time-based rotation
        self._setup_logging()

    def _setup_logging(self):
        """
        Configure logging with time-based rotation.
        Logs will rotate daily with timestamps in filenames.
        """
        # Create logs directory if it doesn't exist
        if not os.path.exists(self.LOGS_DIR):
            os.makedirs(self.LOGS_DIR)
            
        # Configure logging formatter with detailed information
        log_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # Configure the root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Clear any existing handlers
        if root_logger.handlers:
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
        
        # File handler with daily rotation at midnight
        # Logs will have names like crawler.log.2023-03-25
        file_handler = TimedRotatingFileHandler(
            filename=self.LOG_FILE,
            when="midnight",      # Rotate at midnight each day
            interval=1,           # Rotate every day
            backupCount=30,       # Keep 30 days of logs
            encoding="utf-8",
            delay=False
        )
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(logging.INFO)
        
        # Add a suffix with date to rotated files
        file_handler.suffix = "%Y-%m-%d"
        
        # Console handler for terminal output
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        console_handler.setLevel(logging.INFO)
        
        # Add handlers to root logger
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        # Create a named logger for the application
        self.logger = logging.getLogger("EitaaCrawler")
        self.logger.info("Logging system initialized with daily rotation")

# Create a global instance
config = Config()
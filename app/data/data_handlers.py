from abc import ABC, abstractmethod
from datetime import datetime
import os
from app.config import config
from .storage_strategies import LocalStorageStrategy, KafkaStorageStrategy, HybridStorageStrategy

class DataHandler(ABC):
    """
    Abstract base class for data handlers.
    Defines the interface for all data handlers.
    """
    def __init__(self, storage_strategy):
        self.storage_strategy = storage_strategy

    @abstractmethod
    def save(self, data, identifier):
        """Save data with the given identifier"""
        pass

    @abstractmethod
    def load(self, identifier):
        """Load data with the given identifier"""
        pass

    @abstractmethod
    def cleanup(self):
        """Clean up old data"""
        pass

class MessageHandler(DataHandler):
    """
    Handles message data operations.
    Responsible for saving, loading, and cleaning up message data.
    """
    def __init__(self, storage_strategy):
        super().__init__(storage_strategy)
        self.base_dir = config.OUTPUT_DIR

    def save(self, channel_id, messages):
        # Create channel directory
        channel_dir = os.path.join(self.base_dir, channel_id)
        if not os.path.exists(channel_dir):
            os.makedirs(channel_dir)

        # Create timestamped filename
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        timestamped_file = os.path.join(channel_dir, f"messages_{timestamp}.json")

        # Save messages
        self.storage_strategy.save(messages, timestamped_file)

        # Handle legacy file if needed
        if config.CUMULATIVE_JSON_ITERATIONS != 0:
            legacy_file = os.path.join(self.base_dir, f"{channel_id}.json")
            self.storage_strategy.save(messages, legacy_file)

        # Cleanup old files if needed
        if config.CUMULATIVE_JSON_ITERATIONS > 0:
            self.cleanup(channel_id)

    def load(self, channel_id):
        # Try loading from legacy file first
        legacy_file = os.path.join(self.base_dir, f"{channel_id}.json")
        if os.path.exists(legacy_file):
            data = self.storage_strategy.load(legacy_file)
            if data:
                return data

        # Try loading from timestamped files
        channel_dir = os.path.join(self.base_dir, channel_id)
        if os.path.exists(channel_dir):
            files = [f for f in os.listdir(channel_dir) if f.endswith('.json')]
            if files:
                latest_file = sorted(files, reverse=True)[0]
                return self.storage_strategy.load(os.path.join(channel_dir, latest_file))
        
        return []

    def cleanup(self, channel_id):
        if config.CUMULATIVE_JSON_ITERATIONS <= 0:
            return

        channel_dir = os.path.join(self.base_dir, channel_id)
        if not os.path.exists(channel_dir):
            return

        try:
            files = [f for f in os.listdir(channel_dir) if f.endswith('.json')]
            if len(files) > config.CUMULATIVE_JSON_ITERATIONS:
                sorted_files = sorted(files)
                files_to_delete = sorted_files[:-config.CUMULATIVE_JSON_ITERATIONS]
                for file_to_delete in files_to_delete:
                    file_path = os.path.join(channel_dir, file_to_delete)
                    self.storage_strategy.delete(file_path)
        except Exception as e:
            config.logger.error(f"Error cleaning up old message files for {channel_id}: {e}")

class BioHandler(DataHandler):
    """
    Handles bio data operations.
    Responsible for saving, loading, and cleaning up bio data.
    """
    def __init__(self, storage_strategy):
        super().__init__(storage_strategy)
        self.base_dir = config.BIOS_HISTORY_DIR
        self.legacy_file = config.BIO_FILE

    def save(self, bios):
        # Create directory if it doesn't exist
        os.makedirs(self.base_dir, exist_ok=True)
        
        # Create timestamped filename
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        timestamped_file = os.path.join(self.base_dir, f"bios_{timestamp}.json")

        # Save bios
        self.storage_strategy.save(bios, timestamped_file)

        # Handle legacy file if needed
        if config.CUMULATIVE_JSON_ITERATIONS != 0:
            self.storage_strategy.save(bios, self.legacy_file)

        # Cleanup old files if needed
        if config.CUMULATIVE_JSON_ITERATIONS > 0:
            self.cleanup()

    def load(self, channel_id=None):
        # Try loading from legacy file first
        if os.path.exists(self.legacy_file):
            data = self.storage_strategy.load(self.legacy_file)
            if data:
                if channel_id:
                    return next((bio for bio in data if bio.get("channel_id") == channel_id), None)
                return data

        # Try loading from timestamped files
        if os.path.exists(self.base_dir):
            files = [f for f in os.listdir(self.base_dir) if f.endswith('.json')]
            if files:
                latest_file = sorted(files, reverse=True)[0]
                data = self.storage_strategy.load(os.path.join(self.base_dir, latest_file))
                if data:
                    if channel_id:
                        return next((bio for bio in data if bio.get("channel_id") == channel_id), None)
                    return data
        
        return None if channel_id else []

    def cleanup(self):
        if config.CUMULATIVE_JSON_ITERATIONS <= 0:
            return

        if not os.path.exists(self.base_dir):
            return

        try:
            files = [f for f in os.listdir(self.base_dir) if f.endswith('.json')]
            if len(files) > config.CUMULATIVE_JSON_ITERATIONS:
                sorted_files = sorted(files)
                files_to_delete = sorted_files[:-config.CUMULATIVE_JSON_ITERATIONS]
                for file_to_delete in files_to_delete:
                    file_path = os.path.join(self.base_dir, file_to_delete)
                    self.storage_strategy.delete(file_path)
        except Exception as e:
            config.logger.error(f"Error cleaning up old bio files: {e}")

class DataHandlerFactory:
    """
    Factory for creating data handlers.
    Simplifies the creation of properly configured data handlers.
    """
    @staticmethod
    def create_message_handler():
        local_strategy = LocalStorageStrategy()
        kafka_strategy = KafkaStorageStrategy(config.PRODUCER)
        hybrid_strategy = HybridStorageStrategy(local_strategy, kafka_strategy)
        return MessageHandler(hybrid_strategy)

    @staticmethod
    def create_bio_handler():
        local_strategy = LocalStorageStrategy()
        kafka_strategy = KafkaStorageStrategy(config.PRODUCER)
        hybrid_strategy = HybridStorageStrategy(local_strategy, kafka_strategy)
        return BioHandler(hybrid_strategy) 
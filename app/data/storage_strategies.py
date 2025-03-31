from abc import ABC, abstractmethod
import json
import os
from datetime import datetime
from app.config import config
from app.kafka import KafkaManager

class StorageStrategy(ABC):
    """
    Abstract base class for storage strategies.
    Defines the interface for all storage strategies.
    """
    @abstractmethod
    def save(self, data, filepath):
        """Save data to the given filepath"""
        pass

    @abstractmethod
    def load(self, filepath):
        """Load data from the given filepath"""
        pass

    @abstractmethod
    def delete(self, filepath):
        """Delete data at the given filepath"""
        pass

class LocalStorageStrategy(StorageStrategy):
    """
    Strategy for storing data in local files.
    Handles saving, loading, and deleting local files.
    """
    def save(self, data, filepath):
        """Save data to a local file"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        config.logger.debug(f"Saved data to {filepath}")

    def load(self, filepath):
        """Load data from a local file"""
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            config.logger.error(f"Error loading {filepath}: {e}")
            return None

    def delete(self, filepath):
        """Delete a local file"""
        if os.path.exists(filepath):
            os.remove(filepath)
            config.logger.debug(f"Deleted {filepath}")

class KafkaStorageStrategy(StorageStrategy):
    """
    Strategy for storing data in Kafka.
    Handles sending data to Kafka and tracking deliveries.
    """
    def __init__(self, producer=None):
        """Initialize with a Kafka producer or create a new one"""
        # Use the provided producer or create a new KafkaManager
        self.kafka_manager = KafkaManager()
        
        if producer:
            self.kafka_manager.producer = producer
            self.kafka_manager.available = True
        
    def save(self, data, filepath):
        """Send data to Kafka and track for delivery confirmation"""
        return self.kafka_manager.send(config.TOPIC, data, filepath)

    def load(self, filepath):
        """Kafka is not a storage system, so loading is not applicable"""
        return None

    def delete(self, filepath):
        """Remove a filepath from pending deliveries"""
        # Find and remove the file from pending deliveries
        for key, value in list(self.kafka_manager.pending_deliveries.items()):
            if value == filepath:
                del self.kafka_manager.pending_deliveries[key]
                break

class HybridStorageStrategy(StorageStrategy):
    """
    Strategy that combines local and Kafka storage.
    Saves locally first, then sends to Kafka if enabled.
    """
    def __init__(self, local_strategy, kafka_strategy):
        """Initialize with local and Kafka strategies"""
        self.local_strategy = local_strategy
        self.kafka_strategy = kafka_strategy

    def save(self, data, filepath):
        """Save data using both strategies"""
        # First save locally
        self.local_strategy.save(data, filepath)
        
        # Then try to send to Kafka if enabled
        if config.USE_KAFKA:
            return self.kafka_strategy.save(data, filepath)
        return True

    def load(self, filepath):
        """Load data using the local strategy"""
        return self.local_strategy.load(filepath)

    def delete(self, filepath):
        """Delete data using both strategies"""
        self.local_strategy.delete(filepath)
        self.kafka_strategy.delete(filepath) 
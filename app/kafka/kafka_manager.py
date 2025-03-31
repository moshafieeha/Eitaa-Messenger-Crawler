from confluent_kafka import Producer
import json
import os
from app.config import config

class KafkaManager:
    """
    Manages Kafka operations and delivery tracking.
    Handles producer initialization, message sending, and delivery reporting.
    """
    def __init__(self):
        """Initialize the Kafka manager"""
        self.producer = None
        self.available = False
        self.pending_deliveries = {}
        
    def init_producer(self):
        """
        Initialize the Kafka producer
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not config.USE_KAFKA:
            config.logger.debug("Kafka disabled by config")
            return False
            
        try:
            conf = {
                'bootstrap.servers': config.KAFKA_BROKER,
                'retries': 3,
                'request.timeout.ms': 10000
            }
            self.producer = Producer(conf)
            self.available = True
            config.PRODUCER = self.producer
            config.KAFKA_AVAILABLE = True
            config.logger.info("Kafka producer initialized")
            return True
        except Exception as e:
            config.logger.error(f"Kafka producer init failed: {e}")
            self.available = False
            self.producer = None
            config.PRODUCER = None
            config.KAFKA_AVAILABLE = False
            return False
    
    def delivery_report(self, err, msg):
        """
        Callback function to process Kafka delivery reports
        
        Args:
            err: Error object if delivery failed, None if successful
            msg: The delivered message
        """
        msg_key = msg.key().decode('utf-8') if msg.key() else None
        
        if err is not None:
            config.logger.error(f'Message delivery failed: {err} for key: {msg_key}')
            if msg_key in self.pending_deliveries:
                filepath = self.pending_deliveries[msg_key]
                config.logger.info(f'Keeping local file {filepath} due to Kafka delivery failure')
                self.pending_deliveries.pop(msg_key)
        else:
            config.logger.debug(f'Message delivered to {msg.topic()} [{msg.partition()}] for key: {msg_key}')
            if msg_key in self.pending_deliveries:
                filepath = self.pending_deliveries[msg_key]
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        config.logger.info(f'Successfully deleted local file {filepath} after Kafka delivery')
                    self.pending_deliveries.pop(msg_key)
                except Exception as e:
                    config.logger.error(f'Failed to delete local file {filepath}: {e}')
    
    def track_file_for_deletion(self, msg_key, filepath):
        """
        Register a local file to be deleted when Kafka confirms delivery
        
        Args:
            msg_key: The message key used for tracking
            filepath: The path to the file to be deleted on successful delivery
        """
        self.pending_deliveries[msg_key] = filepath
        config.logger.debug(f'Tracking file {filepath} for deletion upon Kafka confirmation with key {msg_key}')
    
    def send(self, topic, data, file_path=None, chunk_size=1000):
        """
        Send data to Kafka and track the file for deletion if file_path is provided
        
        Args:
            topic: The Kafka topic to send to
            data: The data to send (dict or list)
            file_path: The path to the file to track for deletion
            chunk_size: The chunk size for batching large lists
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not config.USE_KAFKA:
            config.logger.debug(f"Kafka disabled for topic {topic}")
            return False
        
        if not self.producer and not self.init_producer():
            config.logger.warning(f"Kafka unavailable for topic {topic}")
            return False
        
        success = True
        try:
            if isinstance(data, dict):
                # Generate a message key based on content
                msg_key = str(data.get("id", "")) + "_" + str(data.get("channel_id", ""))
                if not msg_key.strip("_"):
                    msg_key = f"single_{hash(json.dumps(data))}"
                    
                # Track the file for deletion if provided
                if file_path:
                    self.track_file_for_deletion(msg_key, file_path)
                    
                # Send to Kafka
                self.producer.produce(
                    topic, 
                    key=msg_key.encode('utf-8'),
                    value=json.dumps(data).encode('utf-8'), 
                    callback=self.delivery_report
                )
                config.logger.info(f"Sent 1 item to Kafka topic {topic} with key {msg_key}")
                
            elif isinstance(data, list):
                for i in range(0, len(data), chunk_size):
                    chunk = data[i:i + chunk_size]
                    
                    # Create a batch key
                    batch_key = f"batch_{hash(json.dumps(chunk[:1]))}"
                    
                    # Track the file for deletion if provided
                    if file_path:
                        self.track_file_for_deletion(batch_key, file_path)
                    
                    # Send each item with the batch key
                    for item in chunk:
                        self.producer.produce(
                            topic, 
                            key=batch_key.encode('utf-8'),
                            value=json.dumps(item).encode('utf-8'),
                            callback=self.delivery_report
                        )
                    config.logger.info(f"Sent {len(chunk)} items to Kafka topic {topic} at offset {i} with batch key {batch_key}")
            
            # Flush to ensure delivery callbacks are processed
            self.producer.flush(timeout=10.0)
            config.logger.debug("Producer flush completed")
            
        except Exception as e:
            config.logger.error(f"Kafka send failed for topic {topic}: {e}")
            self.available = False
            self.producer = None
            config.KAFKA_AVAILABLE = False
            config.PRODUCER = None
            success = False
        
        return success 
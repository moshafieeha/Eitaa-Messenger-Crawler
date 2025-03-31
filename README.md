# Eitaa Messenger Crawler

A robust crawler for Eitaa Messenger channels with comprehensive Docker containerization.

## Overview

This application crawls Eitaa Messenger channels, extracts messages and channel information, and stores the data locally and/or in Kafka. The crawler supports:

- Robust error handling for malformed HTML and unexpected page structures
- Adaptive retry mechanisms with exponential backoff
- Alternative CSS selector fallbacks for site changes
- Proxy rotation for avoiding IP blocks
- Kafka integration for real-time data streaming (optional)
- Configurable crawling intervals and data retention
- Docker containerization for easy deployment

## Quick Start

### Prerequisites

- Python 3.7+
- Docker (optional)

### Local Deployment

1. Clone the repository:
```bash
git clone https://github.com/yourusername/Eitaa-Messenger-Crawler.git
cd Eitaa-Messenger-Crawler
```

2. Create your channel list configuration:
```bash
cp config/users.json.example config/users.json
```

3. Edit `config/users.json` to include the channels you want to crawl

4. Run the crawler:
```bash
python -m app.eita_crawler --interval 300
```

Optional flags:
- `--interval`: Crawling interval in seconds (minimum 60)
- `--require-proxies`: Enable proxy mode for requests
- `--kafka`: Enable Kafka integration

### Docker Deployment

1. Set up the configuration as described above

2. Build and start the container:
```bash
docker-compose up -d crawler
```

## Configuration

### Channel List

The channel list is configured in `config/users.json`. This file specifies which Eitaa channels to crawl:

```json
[
  "channel1",
  "channel2",
  "channel3"
]
```

A template file is provided at `config/users.json.example` that you can copy.

### Environment Variables

The following environment variables can be configured in the `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| CHANNELS_FILE | Path to the channels JSON file | config/users.json |
| OUTPUT_DIR | Directory for storing messages | ./output/messages |
| BIOS_DIR | Directory for storing channel bios | ./output/bios |
| LOGS_DIR | Directory for logs | ./logs |
| CRAWL_INTERVAL_SECONDS | Interval between crawl cycles | 1800 |
| CUMULATIVE_JSON_ITERATIONS | Number of previous crawl results to keep | 0 (timestamped only) |
| KAFKA_BROKER | Kafka broker address | localhost:9092 |
| KAFKA_TOPIC | Kafka topic for messages | Eitaa |
| USE_KAFKA | Whether to use Kafka | false |
| REQUIRE_PROXIES | Whether to require proxies | false |
| PROXY_REFRESH_INTERVAL | Interval to refresh proxy list (seconds) | 3600 |

## Docker Architecture

The Docker setup consists of the following services:

- **crawler**: The main Eitaa Messenger crawler application
- **kafka**: Message broker for streaming crawled data (optional)
- **kafka-ui**: Web UI for monitoring Kafka (optional)

### Docker Volumes

The setup uses the following Docker volumes for data persistence:

- **crawler_data**: Stores crawled messages and metadata
- **kafka_data**: Stores Kafka data (if enabled)

## Recent Improvements

The crawler includes recent improvements for better reliability:

- **Modern Browser Emulation**: Updated User-Agent headers to mimic latest Chrome browser
- **Flexible HTML Parsing**: More forgiving HTML structure verification to handle site changes
- **Continuous Operation**: Removed mandatory pauses after consecutive failures for faster crawling
- **Selective Rate Limiting**: Adaptive backoff only when rate limits are detected
- **Better CSS Selectors**: Broader CSS selectors to handle class name changes in the website
- **Relative Imports**: Fixed module import structure to avoid conflicts with other Python packages

## Enhanced Error Handling

The crawler includes comprehensive error handling for robustness:

- **HTTP Error Handling**: Specific handling for 404, 403, 429, and 5xx errors
- **Rate Limiting**: Automatic backoff with decreasing batch size when rate limiting is detected
- **Parsing Resilience**: Multiple parsing strategies for handling HTML structure changes
- **Adaptive Retries**: Exponential backoff for transient failures
- **Connection Recovery**: Automatic recovery from network issues

## Data Structure

The crawler extracts and stores two main types of data:

1. **Messages**: Content of messages from channels
2. **Channel Bios**: Information about the channels being crawled

### Message Format

```json
{
  "_": "message",
  "id": 12345,
  "channel_id": "channelname",
  "url": "https://eitaa.com/channelname/12345",
  "text": "Message content goes here",
  "view_count": 1234,
  "posted_time": "2023-05-01T12:34:56+00:00",
  "crawled_at": "2023-05-02T10:11:12+00:00",
  "extraction_errors": []
}
```

### Channel Bio Format

```json
{
  "_": "channel",
  "channel_id": "channelname",
  "title": "Channel Title",
  "username": "@channelname",
  "follower_count": "1.2k",
  "image_count": "50",
  "video_count": "10",
  "file_count": "5",
  "description": "Channel description text",
  "crawled_at": "2023-05-02T10:11:12+00:00",
  "extraction_errors": []
}
```

## Monitoring

Container logs can be viewed with:

```bash
docker-compose logs -f crawler
```

## Troubleshooting

If you encounter connection issues:

1. Try enabling proxy mode: `--require-proxies`
2. Verify network connectivity to eitaa.com
3. Check logs for specific error messages
4. Consider increasing retry attempts or interval

## License

This project is licensed under the MIT License - see the LICENSE file for details.

#!/bin/bash
set -e

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to display status messages
status() {
  echo -e "${GREEN}[INFO]${NC} $1"
}

warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker and Docker Compose are installed
check_prerequisites() {
  status "Checking prerequisites..."
  
  if ! command -v docker &> /dev/null; then
    error "Docker not found. Please install Docker first."
    exit 1
  fi
  
  if ! command -v docker-compose &> /dev/null; then
    warning "Docker Compose not found. Checking for docker compose plugin..."
    if ! docker compose version &> /dev/null; then
      error "Docker Compose not found. Please install Docker Compose first."
      exit 1
    fi
  fi
  
  status "Prerequisites check passed."
}

# Create necessary directories
create_directories() {
  status "Creating necessary directories..."
  
  mkdir -p config data/output/{messages,bios} data/logs data/meta
  
  if [ ! -f "config/users.json" ]; then
    warning "No users.json found in config directory. Creating a sample one."
    echo '[
  "eitaaNews",
  "eitaastudio" 
]' > config/users.json
  fi
  
  if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    warning "No .env file found. Creating from .env.example"
    cp .env.example .env
  fi
  
  status "Directory setup complete."
}

# Build and start the containers
start_containers() {
  status "Building and starting containers..."
  
  # Check which docker-compose command to use
  if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
  else
    COMPOSE_CMD="docker compose"
  fi
  
  # Build the images
  $COMPOSE_CMD build
  
  # Start the containers
  $COMPOSE_CMD up -d
  
  status "Containers started successfully."
}

# Show logs from containers
show_logs() {
  status "Showing logs from containers. Press Ctrl+C to exit."
  
  if command -v docker-compose &> /dev/null; then
    docker-compose logs -f
  else
    docker compose logs -f
  fi
}

# Main execution
main() {
  status "Starting deployment process for Eitaa Messenger Crawler..."
  
  check_prerequisites
  create_directories
  start_containers
  
  status "Deployment complete!"
  status "Kafka UI is available at: http://localhost:8080"
  status "Container status:"
  
  if command -v docker-compose &> /dev/null; then
    docker-compose ps
  else
    docker compose ps
  fi
  
  # Ask user if they want to see logs
  read -p "Do you want to see container logs? (y/n): " show_logs_choice
  if [[ "$show_logs_choice" =~ ^[Yy]$ ]]; then
    show_logs
  fi
}

# Run the main function
main 
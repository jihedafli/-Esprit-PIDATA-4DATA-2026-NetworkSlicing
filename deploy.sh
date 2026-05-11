#!/bin/bash
# Docker Infrastructure Deployment Script
# For Linux/Mac - Windows users run equivalent commands in PowerShell

set -e  # Exit on error

echo "=========================================="
echo "5G Network Slicing - Docker Deployment"
echo "=========================================="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed or not in PATH"
    echo "Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose is not installed"
    echo "Visit: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✓ Docker is available"
echo "✓ Docker Compose is available"
echo ""

# .env setup
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ .env created"
    echo ""
    echo "NOTE: Update .env with your configuration (passwords, etc.)"
    echo ""
fi

# Create necessary directories
echo "Creating directory structure..."
mkdir -p ml data/raw data/processed data/test logs ssl
echo "✓ Directories created"
echo ""

# Docker Compose command
COMPOSE_CMD="docker-compose"
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
fi

# Pull images (optional, commented out to save time)
# echo "Pulling base images..."
# $COMPOSE_CMD pull mysql nginx

# Build services
echo "Building Docker images..."
$COMPOSE_CMD build

# Start services
echo ""
echo "Starting services..."
$COMPOSE_CMD up -d

# Wait for services
echo "Waiting for services to become healthy..."
sleep 5

# Initialize database (optional - MySQL auto-initializes from init.sql)
echo ""
echo "Database will be auto-initialized from init.sql"
echo "To verify, connect to MySQL:"
echo "  $COMPOSE_CMD exec mysql mysql -u network_user -pnetwork_pass network_slicing_5g"
echo ""

# Show status
echo "Service Status:"
echo "==============="
$COMPOSE_CMD ps

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Access Points:"
echo "  API Gateway:        http://localhost"
echo "  MS1 (QoS):          http://localhost:5001"
echo "  MS2 (Anomaly):      http://localhost:5000"
echo "  MS3 (Dashboard):    http://localhost:5003"
echo "  MS5 (Model Mgmt):   http://localhost:5005"
echo "  MySQL Database:     localhost:3306"
echo ""
echo "Quick Commands:"
echo "  View logs:         $COMPOSE_CMD logs -f"
echo "  Stop services:     $COMPOSE_CMD down"
echo "  Restart:           $COMPOSE_CMD restart"
echo "  Shell into MS1:    $COMPOSE_CMD exec ms1 bash"
echo ""
echo "Health Checks:"
echo "  curl http://localhost/health"
echo "  curl http://localhost:5001/health"
echo "  curl http://localhost:5000/health"
echo ""
echo "For more commands, run: make help"
echo ""

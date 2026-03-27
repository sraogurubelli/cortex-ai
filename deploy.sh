#!/bin/bash

# Cortex-AI Deployment Script
# Deploys all infrastructure and services for the full platform
#
# Usage:
#   ./deploy.sh local      # Local development (Docker Compose)
#   ./deploy.sh k8s        # Kubernetes deployment
#   ./deploy.sh stop       # Stop all services
#   ./deploy.sh logs       # View logs
#   ./deploy.sh health     # Check health status

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# ============================================================================
# Local Development Deployment (Docker Compose)
# ============================================================================

deploy_local() {
    log_info "Starting local deployment with Docker Compose..."

    # Check prerequisites
    if ! command_exists docker; then
        log_error "Docker not found. Please install Docker Desktop."
        exit 1
    fi

    if ! command_exists docker-compose; then
        log_error "docker-compose not found. Please install docker-compose."
        exit 1
    fi

    # Create .env if not exists
    if [ ! -f .env ]; then
        log_warn ".env file not found. Creating from .env.example..."
        if [ -f .env.example ]; then
            cp .env.example .env
            log_info "Created .env file. Please update with your API keys."
        else
            log_error ".env.example not found. Cannot create .env file."
            exit 1
        fi
    fi

    # Start infrastructure services
    log_info "Starting infrastructure services..."
    docker-compose up -d postgres redis qdrant

    # Wait for PostgreSQL
    log_info "Waiting for PostgreSQL to be ready..."
    until docker-compose exec -T postgres pg_isready -U cortex 2>/dev/null; do
        sleep 1
    done
    log_info "PostgreSQL is ready!"

    # Run database migrations
    log_info "Running database migrations..."
    python -m alembic upgrade head || log_warn "Migrations failed or not configured"

    # Start Kafka stack (if enabled)
    if grep -q "KAFKA_ENABLED=true" .env; then
        log_info "Starting Kafka stack..."
        docker-compose up -d zookeeper kafka kafka-ui
        sleep 10  # Wait for Kafka to start
    fi

    # Start StarRocks (if enabled)
    if grep -q "STARROCKS_ENABLED=true" .env; then
        log_info "Starting StarRocks OLAP..."
        docker-compose -f docker-compose.analytics.yml up -d starrocks-fe starrocks-be
        sleep 15  # Wait for StarRocks to start

        # Initialize StarRocks schema
        log_info "Initializing StarRocks schema..."
        docker exec -i starrocks-fe mysql -h localhost -P 9030 -u root < cortex/platform/analytics/schema.sql || log_warn "StarRocks schema initialization failed"
    fi

    # Start Debezium (if StarRocks enabled)
    if grep -q "STARROCKS_ENABLED=true" .env; then
        log_info "Starting Debezium CDC..."
        docker-compose -f docker-compose.analytics.yml up -d debezium-connect debezium-ui
        sleep 10

        # Create Debezium connector
        log_info "Creating Debezium PostgreSQL connector..."
        curl -X POST http://localhost:8083/connectors -H "Content-Type: application/json" -d @deployment/debezium/connector-config.json 2>/dev/null || log_warn "Debezium connector creation skipped"
    fi

    # Start API server
    log_info "Starting API server..."
    log_info "API will be available at http://localhost:8000"
    log_info "API docs at http://localhost:8000/api/docs"

    echo ""
    log_info "🎉 Local deployment complete!"
    echo ""
    log_info "Services:"
    log_info "  - API:           http://localhost:8000"
    log_info "  - API Docs:      http://localhost:8000/api/docs"
    log_info "  - Kafka UI:      http://localhost:8080"
    log_info "  - Debezium UI:   http://localhost:8082"
    echo ""
    log_info "Health checks:"
    log_info "  - Liveness:      curl http://localhost:8000/health"
    log_info "  - Readiness:     curl http://localhost:8000/health/ready"
    log_info "  - Detailed:      curl http://localhost:8000/health/detailed"
    echo ""
    log_info "To start the API server, run:"
    log_info "  uvicorn cortex.api.main:app --host 0.0.0.0 --port 8000 --reload"
}

# ============================================================================
# Kubernetes Deployment
# ============================================================================

deploy_k8s() {
    log_info "Starting Kubernetes deployment..."

    # Check prerequisites
    if ! command_exists kubectl; then
        log_error "kubectl not found. Please install kubectl."
        exit 1
    fi

    # Check if cluster is accessible
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Cannot connect to Kubernetes cluster. Please configure kubectl."
        exit 1
    fi

    # Create namespace and ConfigMap
    log_info "Creating namespace and ConfigMap..."
    kubectl apply -f deployment/k8s/api-config.yaml

    # Prompt for secrets if not exists
    if ! kubectl get secret cortex-secrets -n cortex >/dev/null 2>&1; then
        log_warn "Secrets not found. You need to create secrets manually:"
        echo ""
        echo "kubectl create secret generic cortex-secrets -n cortex \\"
        echo "  --from-literal=database-url='postgresql+asyncpg://cortex:PASSWORD@cortex-postgres:5432/cortex' \\"
        echo "  --from-literal=jwt-secrets='SECRET1,SECRET2' \\"
        echo "  --from-literal=secret-key='VERY_LONG_RANDOM_STRING' \\"
        echo "  --from-literal=openai-api-key='sk-...' \\"
        echo "  --from-literal=anthropic-api-key='sk-ant-...'"
        echo ""
        read -p "Press Enter after creating secrets to continue..."
    fi

    # Deploy API
    log_info "Deploying API..."
    kubectl apply -f deployment/k8s/api-deployment.yaml

    # Wait for deployment to be ready
    log_info "Waiting for deployment to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/cortex-api -n cortex

    # Deploy HPA
    log_info "Deploying Horizontal Pod Autoscaler..."
    kubectl apply -f deployment/k8s/api-hpa.yaml

    # Deploy Ingress
    log_info "Deploying Ingress..."
    kubectl apply -f deployment/k8s/api-ingress.yaml

    # Get service URL
    log_info "Deployment complete!"
    echo ""
    log_info "Services:"
    kubectl get svc -n cortex
    echo ""
    log_info "Pods:"
    kubectl get pods -n cortex
    echo ""
    log_info "Ingress:"
    kubectl get ingress -n cortex
    echo ""
    log_info "To view logs:"
    log_info "  kubectl logs -n cortex -l app=cortex-api --tail=100 -f"
    echo ""
    log_info "To check HPA status:"
    log_info "  kubectl get hpa -n cortex"
}

# ============================================================================
# Stop Services
# ============================================================================

stop_services() {
    log_info "Stopping all services..."

    # Stop Docker Compose services
    if [ -f docker-compose.yml ]; then
        docker-compose down
    fi

    if [ -f docker-compose.analytics.yml ]; then
        docker-compose -f docker-compose.analytics.yml down
    fi

    log_info "All services stopped."
}

# ============================================================================
# View Logs
# ============================================================================

view_logs() {
    log_info "Viewing logs..."

    # Check if running in Kubernetes
    if kubectl get deployment cortex-api -n cortex >/dev/null 2>&1; then
        kubectl logs -n cortex -l app=cortex-api --tail=100 -f
    else
        # Docker Compose logs
        docker-compose logs -f api
    fi
}

# ============================================================================
# Health Check
# ============================================================================

check_health() {
    log_info "Checking health status..."

    # Determine API URL
    API_URL="http://localhost:8000"
    if kubectl get deployment cortex-api -n cortex >/dev/null 2>&1; then
        # Get service URL from Kubernetes
        API_URL=$(kubectl get svc cortex-api -n cortex -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "localhost:8000")
        API_URL="http://${API_URL}"
    fi

    echo ""
    log_info "Testing health endpoints at $API_URL..."
    echo ""

    # Liveness probe
    echo "Liveness probe:"
    curl -s "${API_URL}/health" | jq '.' || echo "Failed"
    echo ""

    # Readiness probe
    echo "Readiness probe:"
    curl -s "${API_URL}/health/ready" | jq '.' || echo "Failed"
    echo ""

    # Startup probe
    echo "Startup probe:"
    curl -s "${API_URL}/health/startup" | jq '.' || echo "Failed"
    echo ""

    # Detailed health
    echo "Detailed health:"
    curl -s "${API_URL}/health/detailed" | jq '.' || echo "Failed"
    echo ""

    # WebSocket stats (if enabled)
    echo "WebSocket stats:"
    curl -s "${API_URL}/health/detailed" | jq '.checks.websocket' || echo "WebSocket not enabled"
    echo ""
}

# ============================================================================
# Main
# ============================================================================

case "${1:-help}" in
    local)
        deploy_local
        ;;
    k8s)
        deploy_k8s
        ;;
    stop)
        stop_services
        ;;
    logs)
        view_logs
        ;;
    health)
        check_health
        ;;
    *)
        echo "Cortex-AI Deployment Script"
        echo ""
        echo "Usage:"
        echo "  ./deploy.sh local      Deploy locally with Docker Compose"
        echo "  ./deploy.sh k8s        Deploy to Kubernetes"
        echo "  ./deploy.sh stop       Stop all services"
        echo "  ./deploy.sh logs       View logs"
        echo "  ./deploy.sh health     Check health status"
        echo ""
        echo "Example:"
        echo "  ./deploy.sh local      # Start local development"
        echo "  ./deploy.sh health     # Check all health endpoints"
        echo "  ./deploy.sh stop       # Stop everything"
        exit 1
        ;;
esac

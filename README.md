# Support Ticket Classification & Routing

A production-ready API for classifying and routing support tickets using ML.

## Features

- **Classification**: DistilBERT-based ticket categorization (technical, billing, account, security, etc.)
- **Routing**: Intelligent team assignment with priority and SLA calculation
- **Async Inference**: Batched async inference pipeline with configurable timeouts
- **Observability**: Structured JSON logging, Prometheus metrics, health endpoints
- **Security**: PII redaction, rate limiting, input validation
- **Production Ready**: Lifespan management, graceful shutdown, structured errors

## API Endpoints

- `POST /api/v1/classify` - Classify a single ticket
- `POST /api/v1/classify/batch` - Classify multiple tickets
- `GET /api/v1/health` - Basic health check
- `GET /api/v1/health/live` - Liveness probe
- `GET /api/v1/health/ready` - Readiness probe with component checks
- `GET /api/v1/metrics` - Prometheus metrics

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run development server
uvicorn app.main:app --reload

# Run with Docker
docker-compose up
```

## Configuration

Environment variables (or `.env` file):

```bash
ENVIRONMENT=development
LOG_LEVEL=INFO
LOG_FORMAT=console
MODEL_PATH=models/distilbert
REDIS_URL=redis://localhost:6379/0
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60
```

## Testing

```bash
pytest
pytest --cov=app
```

## Monitoring

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
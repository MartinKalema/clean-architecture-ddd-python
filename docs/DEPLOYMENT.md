# Deployment Guide

## Architecture Overview

```
                    ┌─────────────┐
                    │   Clients   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │    Nginx    │
                    │   (L7 LB)   │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
   │  API 1  │  ...  │  API 4  │  ...  │  API 8  │
   └────┬────┘       └────┬────┘       └────┬────┘
        │                 │                  │
        └─────────────────┼──────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
   │  Redis  │      │PgBouncer│      │RabbitMQ │
   │ (Cache) │      │ (Pool)  │      │ (Queue) │
   └─────────┘      └────┬────┘      └─────────┘
                         │
                   ┌─────▼─────┐
                   │PostgreSQL │
                   └───────────┘
```

## Local Development

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Make (optional)

### Quick Start

```bash
# Start all services
docker compose up --build

# Or with load testing profile
docker compose --profile loadtest up --build --scale locust-worker=4
```

### Service Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| API | http://localhost:8000 | Main application |
| Locust | http://localhost:8089 | Load testing UI |
| RabbitMQ | http://localhost:15672 | Message broker management |
| PgBouncer | localhost:6432 | Connection pooling |
| PostgreSQL | localhost:5432 | Database (direct) |
| Redis | localhost:6379 | Cache |
| etcd | localhost:2379 | Configuration |

### Environment Variables

Create `.env.docker` for Docker or `.env` for local development:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://library:library_secret@pgbouncer:6432/library_db

# etcd Configuration
ETCD_HOST=etcd
ETCD_PORT=2379

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_ENABLED=true
REDIS_CACHE_TTL=300

# SendGrid (optional)
SENDGRID_API_KEY=your-api-key
SENDGRID_FROM_EMAIL=noreply@example.com
```

## Docker Compose Services

### Core Application

```yaml
api:
  build: .
  depends_on:
    - pgbouncer
    - redis
    - rabbitmq
    - etcd
```

The API runs with 2 Uvicorn workers per container. Scale horizontally with multiple containers behind nginx.

### Nginx Load Balancer

- Round-robin load balancing across 8 API instances
- Connection keepalive for performance
- Health check routing

Configuration: `deploy/nginx/nginx.conf`

### PgBouncer Connection Pooling

| Setting | Value | Purpose |
|---------|-------|---------|
| `POOL_MODE` | transaction | Release connections after each transaction |
| `MAX_CLIENT_CONN` | 10000 | Maximum client connections |
| `MAX_DB_CONNECTIONS` | 400 | Maximum PostgreSQL connections |
| `DEFAULT_POOL_SIZE` | 300 | Connections per pool |
| `MIN_POOL_SIZE` | 50 | Minimum idle connections |

### PostgreSQL

Tuned for high concurrency:

```yaml
command:
  - "postgres"
  - "-c" "max_connections=500"
  - "-c" "shared_buffers=512MB"
  - "-c" "effective_cache_size=1GB"
  - "-c" "work_mem=32MB"
```

### Redis Cache

- 256MB memory limit
- LRU eviction policy
- 5-minute default TTL

### etcd Configuration

Centralized configuration management. Keys are stored under `/config/` prefix:

```
/config/database/url
/config/redis/enabled
/config/circuit_breakers/rabbitmq/timeout
```

## Production Deployment

### Google Cloud Run

#### Prerequisites

1. Enable Cloud SQL with managed PgBouncer
2. Set pool mode to `Transaction`
3. Configure Cloud SQL Auth Proxy

#### Service Configuration

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: library-service
spec:
  template:
    metadata:
      annotations:
        run.googleapis.com/execution-environment: gen2
        autoscaling.knative.dev/maxScale: "100"
        run.googleapis.com/cloudsql-instances: PROJECT:REGION:INSTANCE
    spec:
      containers:
        - image: gcr.io/PROJECT/library-app:latest
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              value: "postgresql+asyncpg://user:pass@/db?host=/cloudsql/PROJECT:REGION:INSTANCE"
            - name: DB_POOL_SIZE
              value: "50"
          resources:
            limits:
              cpu: "1000m"
              memory: "512Mi"
```

### Kubernetes

#### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: library-api
spec:
  replicas: 8
  selector:
    matchLabels:
      app: library-api
  template:
    spec:
      containers:
        - name: api
          image: library-app:latest
          ports:
            - containerPort: 8000
          resources:
            requests:
              cpu: "500m"
              memory: "256Mi"
            limits:
              cpu: "1000m"
              memory: "512Mi"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
```

#### Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: library-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: library-api
  minReplicas: 4
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

## Load Testing

### Running Load Tests

```bash
# Start with load test profile
docker compose --profile loadtest up --build --scale locust-worker=4

# Access Locust UI
open http://localhost:8089
```

### Test Shapes

| Shape | File | Description |
|-------|------|-------------|
| Stages | `run_stages.py` | Ramps to 10k users |
| Stress | `run_stress.py` | Finds breaking point |
| Soak | `run_soak.py` | Extended duration |
| Spike | `run_spike.py` | Sudden load bursts |

### Performance Benchmarks

At 10,000 concurrent users:

| Metric | Target | Achieved |
|--------|--------|----------|
| Error Rate | <1% | 0% |
| P50 Latency | <2s | 1.5s |
| P95 Latency | <5s | 4.8s |
| P99 Latency | <10s | 6.6s |
| RPS | >1000 | 1219 |

## Monitoring

### Health Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Basic liveness check |
| `GET /health/ready` | Readiness with dependencies |
| `GET /health/circuit-breakers` | Circuit breaker status |

### Key Metrics

- Request latency (P50, P95, P99)
- Error rate
- Database connection pool utilization
- Cache hit rate
- Circuit breaker state

## Troubleshooting

### High Latency

1. Check PgBouncer pool utilization
2. Verify Redis cache is enabled and hitting
3. Review slow query logs
4. Check for connection pool exhaustion

### Connection Errors

1. Increase `DEFAULT_POOL_SIZE` in PgBouncer
2. Check `max_connections` in PostgreSQL
3. Verify network connectivity between services

### 502 Bad Gateway

1. Check if API instances are healthy
2. Review nginx upstream configuration
3. Increase nginx `proxy_read_timeout`
4. Scale up API instances

### Database Deadlocks

1. Review transaction isolation levels
2. Check for missing indexes
3. Ensure consistent lock ordering

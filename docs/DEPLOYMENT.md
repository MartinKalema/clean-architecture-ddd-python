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
   │  Redis  │      │PgBouncer│      │  Kafka  │
   │ (Cache) │      │ (Pool)  │      │ (Events)│
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
# Start the API plus its required event pipeline and reservation reaper
docker compose up --build

# Add optional table CDC and the Elasticsearch read model
docker compose --profile cdc up --build

# Or with load testing profile
docker compose --profile loadtest up --build --scale locust-worker=4
```

### Service Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| API | http://localhost:8000 | Main application |
| Locust | http://localhost:8089 | Load testing UI |
| Kafka | localhost:9092 | Domain-event and CDC broker |
| Debezium | http://localhost:8083 | Outbox/CDC connector API |
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

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:29092

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
    migrator:
      condition: service_completed_successfully
    pgbouncer:
      condition: service_healthy
    redis:
      condition: service_healthy
```

The API runs with one Uvicorn worker per container and scales horizontally
behind Nginx. The default stack also starts Zookeeper, Kafka, Debezium's
transactional-outbox connector, two event-worker replicas, the reservation
reaper, and bounded outbox/durable-state cleaners. The first three complete
business workflows; the cleaners keep retained event data bounded. The `cdc` profile adds only
the optional table-CDC/Elasticsearch projection path.

The default topology also runs `debezium-outbox-monitor`, whose health probe
checks both connector and task state continuously after registration. Worker
containers expose process health, while the reservation reaper touches a
success-only heartbeat; repeated sweep failures make that container unhealthy
instead of being hidden by its retry loop. API containers probe `/health/ready`
rather than liveness.

The cleaner defaults to 90-day retention and deletes at most 10,000 rows
per hourly run. Retention uses the database insertion timestamp, not the domain
event occurrence timestamp, so delayed historical events receive a full
retention window. Compose starts the cleaner only after the outbox connector
and task report `RUNNING`; the same dependency is mandatory in other
environments. Keep the Debezium replication slot durable: a lagging connector
can still read retained WAL after rows are pruned, but a recreated slot cannot
recover pruned history. Every cleanup run therefore verifies that the declared
slot exists in the current database, is active, has a confirmed flush LSN, and
remains below `OUTBOX_MAX_SLOT_LAG_BYTES`. The cutoff comes from PostgreSQL's
clock, and slot state is checked before and after every delete batch so a failed
fence rolls the transaction back. Correctness topics retain 30 days, leaving a
60-day database recovery margin. Increase both horizons before a longer outage.

The durable-state cleaner keeps command receipts for 30 days, terminal borrow
operations and processed inbox claims for 120 days, and quarantined payloads
for 365 days. The inbox horizon exceeds the 90-day outbox replay horizon, so
deduplication evidence cannot expire while its source event remains replayable.
Archive quarantine evidence externally before extending an investigation past
its maximum retention; it may contain patron data.

### Database Schema Ownership

Alembic is the sole PostgreSQL schema owner. Deployments run `alembic upgrade
head` once, before application processes. API startup only verifies that the
database's `alembic_version` exactly equals the repository head; it fails fast
instead of creating or upgrading tables.

The migration role must own schema DDL. The baseline needs the trusted
`pg_trgm` extension; least-privilege environments should have a database
administrator install it before deployment.

In Docker Compose, this ordering is enforced by the one-shot `migrator`
service and `depends_on: condition: service_completed_successfully`. Apply the
same expand/migrate/verify ordering in Kubernetes or managed deployments.

This application has not been released. Revision `baseline_20260712` is
therefore the only supported schema and must be applied to an empty database. Development
databases created from earlier revisions must be dropped and recreated; the
repository intentionally contains no in-place upgrade, backfill, or old-data
conversion code.

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
/config/circuit_breakers/sendgrid/timeout
```

## Production Deployment

### Required Topology

The snippets below describe the API process only; deploying that process by
itself is not a functional system. Every production environment must also
provide:

- a one-shot `alembic upgrade head` job before any release process starts;
- PostgreSQL through a healthy PgBouncer path and etcd configuration;
- durable Kafka plus Kafka Connect/Debezium with the outbox connector and task
  both `RUNNING`;
- one or more `python scripts/run_event_worker.py` processes using the shared
  consumer group;
- exactly one active `python scripts/run_reservation_reaper.py` process (or a
  leader-elected equivalent).

Domain-event workers retry transient state reconciliation indefinitely with
bounded backoff. Alert on worker restarts, outbox connector/task state,
consumer lag approaching the reservation TTL, and any DLQ record.
`/health/ready` covers the API request path; it is not a substitute for these
pipeline health signals.

### Google Cloud Run

#### Prerequisites

1. Enable Cloud SQL with managed PgBouncer
2. Set pool mode to `Transaction`
3. Configure Cloud SQL Auth Proxy

#### API Service Component

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

Use managed Kafka/Kafka Connect or separately hosted equivalents, plus Cloud
Run worker services/jobs for the event-worker, reaper, and migrator commands
listed above. Do not route client traffic to the API service until those
release checks pass.

### Kubernetes

#### API Deployment Component

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

Create a pre-deploy Kubernetes `Job` with command `alembic upgrade head`, an
`event-worker` Deployment (replicas bounded by Kafka partitions), and a
single-replica `reservation-reaper` Deployment. Kafka/Connect may be managed
by an operator, but rollout health must verify the outbox connector and task
states before the API Service is made ready for traffic.

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

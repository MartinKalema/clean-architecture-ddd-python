# Cloud Run Deployment Guide: Cloud SQL Managed PgBouncer

## Overview
Since you are using Cloud SQL, the **Managed PgBouncer** is the best choice. It eliminates the need for a sidecar container, reducing complexity and operational overhead.

## Prerequisites
1.  **Enable PgBouncer**: Go to your Cloud SQL instance in Google Cloud Console -> Connections -> Enable PgBouncer.
2.  **Configure**: Set `Pool Mode` to `Transaction` (recommended for high concurrency).

## Application Configuration

Your application is already tuned for this setup.

### 1. Connection String
Connect to the Cloud SQL instance normally. The managed pooler intercepts connections on the standard port (or a specific port depending on how you connect).

*   **Via Cloud SQL Auth Proxy (Recommended for Cloud Run)**:
    The proxy automatically handles the connection. You just need to ensure your application connects to the proxy.

### 2. Required Code Settings (Already Done)
We verified these settings locally, and they are **required** for the managed pooler too:
*   **`statement_cache_size=0`**: We set this in `src/infrastructure/external/database.py`. This is critical for `transaction` mode compatibility.
*   **`DB_POOL_SIZE`**: Set this to match your Cloud Run instance concurrency (e.g., 50).
    *   *Note*: With managed PgBouncer, the "global" pool is managed by Cloud SQL. Your app just needs enough connections to keep its local workers busy.

## Service Configuration (`service.yaml`)

Using the managed pooler simplifies your `service.yaml` significantly (no sidecar needed).

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
        # Mount the Cloud SQL Auth Proxy automatically
        run.googleapis.com/cloudsql-instances: PROJECT_ID:REGION:INSTANCE_NAME
    spec:
      containers:
        - image: gcr.io/PROJECT_ID/library-app:latest
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              # Connect via the built-in Auth Proxy socket
              # The proxy handles the secure tunnel to Cloud SQL (and its PgBouncer)
              value: "postgresql+asyncpg://library:library_secret@/library_db?host=/cloudsql/PROJECT_ID:REGION:INSTANCE_NAME"
            - name: DB_POOL_SIZE
              value: "50"  # Keep small per instance
            - name: DB_MAX_OVERFLOW
              value: "10"
          resources:
            limits:
              cpu: "1000m"
              memory: "512Mi"
```

## Why this is better
1.  **Simplicity**: No extra container to manage.
2.  **Performance**: Google optimizes the pooler for the specific instance type.
3.  **Security**: Uses standard Cloud SQL Auth Proxy (IAM authentication).

## Alternative: Sidecar Pattern
(Only use this if you need custom `pgbouncer.ini` settings not supported by the managed service, like custom auth queries or extremely specific timeout logic.)
*   *See previous version of this guide for sidecar configuration.*

import uvicorn

if __name__ == "__main__":
    # One worker per container: scaling is horizontal via API container
    # replicas (api-1..api-8 behind nginx). A single process per container
    # keeps circuit breaker state and /health/circuits coherent — with
    # multiple workers, each process holds its own breaker registry and
    # health checks sample a random one.
    uvicorn.run("src.presentation.api.main:app", host="0.0.0.0", port=8000, workers=1, backlog=8192, limit_concurrency=10000)

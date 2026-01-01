#!/bin/bash

# Wait for Debezium to be ready
echo "Waiting for Debezium Connect to be ready..."
until curl -s http://localhost:8083/connectors > /dev/null 2>&1; do
    sleep 2
done
echo "Debezium Connect is ready!"

# Register the connector
echo "Registering PostgreSQL connector..."
curl -X POST \
    -H "Content-Type: application/json" \
    --data @"$(dirname "$0")/register-connector.json" \
    http://localhost:8083/connectors

echo ""
echo "Connector registered. Checking status..."
sleep 2
curl -s http://localhost:8083/connectors/library-connector/status | jq .

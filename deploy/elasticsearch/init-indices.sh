#!/bin/bash

ES_URL="${ELASTICSEARCH_URL:-http://localhost:9200}"
SCRIPT_DIR="$(dirname "$0")"

echo "Waiting for Elasticsearch to be ready..."
until curl -s "$ES_URL/_cluster/health" > /dev/null 2>&1; do
    sleep 2
done
echo "Elasticsearch is ready!"

echo "Creating indices..."

# Create books index
echo "Creating books index..."
curl -X PUT "$ES_URL/books" \
    -H "Content-Type: application/json" \
    -d @"$SCRIPT_DIR/mappings/books.json"
echo ""

# Create patrons index
echo "Creating patrons index..."
curl -X PUT "$ES_URL/patrons" \
    -H "Content-Type: application/json" \
    -d @"$SCRIPT_DIR/mappings/patrons.json"
echo ""

# Create loans index
echo "Creating loans index..."
curl -X PUT "$ES_URL/loans" \
    -H "Content-Type: application/json" \
    -d @"$SCRIPT_DIR/mappings/loans.json"
echo ""

echo "All indices created successfully!"
curl -s "$ES_URL/_cat/indices?v"

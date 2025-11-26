"""
Workers for background processing.

- event_worker: Consumes events from RabbitMQ and dispatches to handlers
- outbox_worker: Processes transactional outbox for reliable event delivery
"""

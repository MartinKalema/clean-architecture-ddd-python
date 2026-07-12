"""External clients.

Import concrete clients from their modules. Keeping this package initializer
side-effect free prevents importing Redis/PostgreSQL from eagerly requiring
unrelated etcd or SendGrid SDKs.
"""

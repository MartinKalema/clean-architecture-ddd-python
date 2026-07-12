"""Inbound-agnostic application ports implemented by outer adapters."""

from .exceptions import EmailDeliveryException
from .interfaces import (
    EventDeliveryIdentity,
    ICache,
    ICommandHandler,
    IConfigurationProvider,
    IEmailService,
    IEventDispatcher,
    IEventHandler,
    ILogger,
)
from .borrow_operations import (
    BorrowOperation,
    BorrowOperationStatus,
    IBorrowOperationRepository,
)
from .borrower_directory import BorrowerProfile, IBorrowerDirectory
from .clock import IClock
from .idempotency import (
    CommandReceipt,
    ICommandReceiptRepository,
    IdempotencyKey,
    command_fingerprint,
    require_matching_receipt,
)
from .unit_of_work import (
    ICatalogApplicationUnitOfWork,
    ILendingApplicationUnitOfWork,
    IPatronApplicationUnitOfWork,
)

__all__ = [
    "EmailDeliveryException",
    "EventDeliveryIdentity",
    "ICache",
    "ICommandHandler",
    "IConfigurationProvider",
    "IEmailService",
    "IEventDispatcher",
    "IEventHandler",
    "ILogger",
    "IClock",
    "IdempotencyKey",
    "CommandReceipt",
    "ICommandReceiptRepository",
    "command_fingerprint",
    "require_matching_receipt",
    "BorrowOperation",
    "BorrowOperationStatus",
    "IBorrowOperationRepository",
    "BorrowerProfile",
    "IBorrowerDirectory",
    "ICatalogApplicationUnitOfWork",
    "ILendingApplicationUnitOfWork",
    "IPatronApplicationUnitOfWork",
]

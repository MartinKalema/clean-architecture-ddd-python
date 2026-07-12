from __future__ import annotations

import asyncio

import click
from dependency_injector.wiring import Provide, inject

from src.application.command_handlers import BorrowBookCommand, BorrowBookResult
from src.application.ports import ICommandHandler
from src.container import CliContainer

@click.command()
@click.argument("book_id")
@click.argument("borrower_email")
@inject
def borrow(
    book_id: str,
    borrower_email: str,
    operation: ICommandHandler[BorrowBookCommand, BorrowBookResult] = Provide[
        CliContainer.borrow_book
    ]
):
    """Borrow a book from the catalog."""
    try:
        command = BorrowBookCommand(book_id=book_id, borrower_email=borrower_email)
        result = asyncio.run(operation.handle(command))
        click.echo(
            f"Borrow requested: {result.title} "
            f"(reservation {result.reservation_id})"
        )
    except Exception as e:
        click.echo(f"Error: {e}")

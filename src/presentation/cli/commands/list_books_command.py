from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import click
from dependency_injector.wiring import Provide, inject

from src.application.query_handlers import ListBooksQuery
from src.container import CliContainer

if TYPE_CHECKING:
    from src.application.query_handlers import ListBooksHandler


@click.command()
@click.option("--available", is_flag=True, help="Show only available books")
@click.option("--borrowed", is_flag=True, help="Show only borrowed books")
@inject
def list(
    available: bool,
    borrowed: bool,
    handler: ListBooksHandler = Provide[CliContainer.list_books_handler]
):
    """List all books in the catalog."""
    query = ListBooksQuery(only_available=available, only_borrowed=borrowed)
    books = asyncio.run(handler.handle(query))

    if not books:
        click.echo("No books found.")
        return

    for book in books:
        status = "Borrowed" if book.is_borrowed else "Available"
        click.echo(f"[{status}] {book.title} by {book.author} (ID: {book.id})")

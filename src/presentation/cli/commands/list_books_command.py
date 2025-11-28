from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import click
from dependency_injector.wiring import inject, Provide

from src.container import Container

if TYPE_CHECKING:
    from src.application.use_cases.list_books import ListBooks

@click.command()
@inject
def list(
    use_case: ListBooks = Provide[Container.list_books_use_case]
):
    books = asyncio.run(use_case.execute())
    if not books:
        click.echo("No books found.")
        return
    
    for book in books:
        status = "Borrowed" if book.is_borrowed else "Available"
        click.echo(f"[{status}] {book.title} by {book.author} (ID: {book.id})")

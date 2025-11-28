from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import click
from dependency_injector.wiring import inject, Provide

from src.container import Container
from src.application.commands import AddBookCommand

if TYPE_CHECKING:
    from src.application.commands import AddBookHandler


@click.command()
@click.argument("title")
@click.argument("author")
@inject
def add(
    title: str,
    author: str,
    handler: AddBookHandler = Provide[Container.add_book_handler]
):
    """Add a new book to the catalog."""
    command = AddBookCommand(title=title, author=author)
    result = asyncio.run(handler.handle(command))
    click.echo(f"Book added: {result.title} by {result.author} (ID: {result.id})")

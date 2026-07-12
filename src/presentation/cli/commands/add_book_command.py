from __future__ import annotations

import asyncio

import click
from dependency_injector.wiring import Provide, inject

from src.application.command_handlers import AddBookCommand, AddBookResult
from src.application.ports import ICommandHandler
from src.container import CliContainer

@click.command()
@click.argument("title")
@click.argument("author")
@inject
def add(
    title: str,
    author: str,
    operation: ICommandHandler[AddBookCommand, AddBookResult] = Provide[
        CliContainer.add_book
    ]
):
    """Add a new book to the catalog."""
    command = AddBookCommand(title=title, author=author)
    result = asyncio.run(operation.handle(command))
    click.echo(f"Book added: {result.title} by {result.author} (ID: {result.id})")

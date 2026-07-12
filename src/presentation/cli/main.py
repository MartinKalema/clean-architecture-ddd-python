import asyncio

import click

from src.composition.bootstrap import bootstrap_container
from src.composition.lifecycle import cli_resources
from src.composition.runtime_config import ProcessRole
from src.container import CliContainer
from src.presentation.cli.commands.add_book_command import add
from src.presentation.cli.commands.borrow_book_command import borrow
from src.presentation.cli.commands.list_books_command import list


@click.group()
def cli():
    pass

cli.add_command(add)
cli.add_command(list)
cli.add_command(borrow)

if __name__ == "__main__":
    container = CliContainer()
    bootstrap_container(container, ProcessRole.CLI)
    resources = cli_resources(container)
    try:
        cli()
    finally:
        asyncio.run(resources.close())

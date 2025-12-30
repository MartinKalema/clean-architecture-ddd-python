import click

from src.container import Container
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
    container = Container()
    etcd_adapter = container.etcd_adapter()
    etcd_adapter.load()
    container.configurations.from_dict(etcd_adapter.get_all())
    container.wire(modules=[
        "src.presentation.cli.commands.add_book_command",
        "src.presentation.cli.commands.list_books_command",
        "src.presentation.cli.commands.borrow_book_command"
    ])
    cli()

import click
import asyncio
from dependency_injector.wiring import inject, Provide
from src.container import Container
from src.application.use_cases.add_book import AddBook
from src.application.dto.book_dto import AddBookInputDto

@click.command()
@click.argument("title")
@click.argument("author")
@inject
def add(
    title: str,
    author: str,
    use_case: AddBook = Provide[Container.add_book_use_case]
):
    input_dto = AddBookInputDto(title=title, author=author)
    output_dto = asyncio.run(use_case.execute(input_dto))
    click.echo(f"Book added: {output_dto.title} by {output_dto.author} (ID: {output_dto.id})")

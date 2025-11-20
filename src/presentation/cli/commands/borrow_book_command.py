import click
import asyncio
from dependency_injector.wiring import inject, Provide
from src.container import Container
from src.application.use_cases.borrow_book import BorrowBook
from src.application.dto.book_dto import BorrowBookInputDto

@click.command()
@click.argument("book_id")
@inject
def borrow(
    book_id: str,
    use_case: BorrowBook = Provide[Container.borrow_book_use_case]
):
    try:
        input_dto = BorrowBookInputDto(book_id=book_id)
        output_dto = asyncio.run(use_case.execute(input_dto))
        click.echo(f"Successfully borrowed: {output_dto.title}")
    except Exception as e:
        click.echo(f"Error: {e}")

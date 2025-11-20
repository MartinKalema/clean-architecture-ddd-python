import click
import asyncio
from dependency_injector.wiring import inject, Provide
from src.container import Container
from src.application.use_cases.add_book import AddBook
from src.application.use_cases.list_books import ListBooks
from src.application.use_cases.borrow_book import BorrowBook
from src.application.dto.book_dto import AddBookInputDto, BorrowBookInputDto

@click.group()
def cli():
    pass

@cli.command()
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

@cli.command()
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

@cli.command()
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

if __name__ == "__main__":
    container = Container()
    container.wire(modules=[__name__])
    cli()

from typing import List
from src.domain.interfaces.book_repository import BookRepository
from src.application.use_cases.add_book import AddBook
from src.application.use_cases.list_books import ListBooks
from src.application.use_cases.borrow_book import BorrowBook
from src.application.dto.book_dto import AddBookInputDto, AddBookOutputDto, BookOutputDto, BorrowBookInputDto, BorrowBookOutputDto

class BookController:
    def __init__(self, repository: BookRepository):
        self.repository = repository

    def add_book(self, title: str, author: str) -> AddBookOutputDto:
        use_case = AddBook(self.repository)
        input_dto = AddBookInputDto(title=title, author=author)
        return use_case.execute(input_dto)

    def list_books(self) -> List[BookOutputDto]:
        use_case = ListBooks(self.repository)
        return use_case.execute()

    def borrow_book(self, book_id: str) -> BorrowBookOutputDto:
        use_case = BorrowBook(self.repository)
        input_dto = BorrowBookInputDto(book_id=book_id)
        return use_case.execute(input_dto)

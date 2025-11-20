from dataclasses import dataclass

@dataclass
class AddBookInputDto:
    title: str
    author: str

@dataclass
class AddBookOutputDto:
    id: str
    title: str
    author: str
    is_borrowed: bool

@dataclass
class BookOutputDto:
    id: str
    title: str
    author: str
    is_borrowed: bool

@dataclass
class BorrowBookInputDto:
    book_id: str

@dataclass
class BorrowBookOutputDto:
    id: str
    title: str
    author: str
    is_borrowed: bool

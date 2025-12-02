import pytest

from src.domain.catalog import Author, BookId, Title, ValidationException


def test_book_id_creation():
    book_id = BookId.next_id()
    assert book_id.value is not None
    assert isinstance(book_id.value, str)


def test_book_id_empty_validation():
    with pytest.raises(ValidationException, match="BookId cannot be empty"):
        BookId("")


def test_title_creation():
    title = Title("Clean Code")
    assert title.value == "Clean Code"


def test_title_empty_validation():
    with pytest.raises(ValidationException, match="Title cannot be empty"):
        Title("")


def test_title_length_validation():
    long_title = "a" * 101
    with pytest.raises(ValidationException, match="Title cannot be longer than 100 characters"):
        Title(long_title)


def test_author_creation():
    author = Author("Robert C. Martin")
    assert author.value == "Robert C. Martin"


def test_author_empty_validation():
    with pytest.raises(ValidationException, match="Author cannot be empty"):
        Author("")

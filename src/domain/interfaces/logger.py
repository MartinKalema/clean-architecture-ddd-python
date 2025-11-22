from typing import Protocol

class Logger(Protocol):
    def info(self, message: str) -> None:
        ...

    def error(self, message: str, exception: Exception = None) -> None:
        ...

    def warning(self, message: str) -> None:
        ...

    def debug(self, message: str) -> None:
        ...

from typing import Protocol

class EmailService(Protocol):
    async def send_email(self, to_email: str, subject: str, content: str) -> None:
        ...

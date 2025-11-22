from src.infrastructure.external.sendgrid_client import SendGridClient
from src.domain.interfaces.email_service import EmailService

class SendGridEmailService(EmailService):
    def __init__(self, client: SendGridClient, from_email: str, admin_email: str):
        self.client = client
        self.from_email = from_email
        self.admin_email = admin_email

    async def send_email(self, to_email: str, subject: str, content: str) -> None:
        self.client.send(
            from_email=self.from_email,
            to_email=to_email,
            subject=subject,
            content_str=content,
            cc_email=self.admin_email
        )
        print(f"[SendGridAdapter] Email sent to {to_email} (CC: {self.admin_email})")

from src.infrastructure.external.sendgrid_client import SendGridClient
from src.domain.interfaces.email_service import EmailService
from src.domain.interfaces.logger import Logger

class SendGridEmailService(EmailService):
    def __init__(self, client: SendGridClient, from_email: str, admin_email: str, logger: Logger):
        self.client = client
        self.from_email = from_email
        self.admin_email = admin_email
        self.logger = logger

    async def send_email(self, to_email: str, subject: str, content: str) -> None:
        try:
            # Send email with CC to admin
            self.client.send(
                from_email=self.from_email,
                to_email=to_email,
                subject=subject,
                content_str=content,
                cc_email=self.admin_email
            )
            self.logger.info(f"[SendGridAdapter] Email sent to {to_email} (CC: {self.admin_email})")
        except Exception as e:
            from src.infrastructure.exceptions.infrastructure_exceptions import EmailServiceException
            self.logger.error(f"Failed to send email to {to_email}", exception=e)
            raise EmailServiceException(f"Failed to send email to {to_email}: {str(e)}", original_exception=e)

import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content, Cc

from src.domain.shared_kernel import Logger


class SendGridClient:
    def __init__(self, api_key: str, logger: Logger):
        self.sg = sendgrid.SendGridAPIClient(api_key=api_key)
        self.logger = logger

    def send(self, from_email: str, to_email: str, subject: str, content_str: str, cc_email: str = None):
        message = Mail(
            from_email=Email(from_email),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", content_str)
        )

        if cc_email:
            message.add_cc(Cc(cc_email))

        try:
            response = self.sg.client.mail.send.post(request_body=message.get())
            self.logger.info(f"Email sent to {to_email}. Status: {response.status_code}")
            return response.status_code
        except Exception as e:
            self.logger.error(f"SendGrid API Error: {e}", exception=e)
            raise e

from src.infrastructure.external.sendgrid_client import SendGridClient
from src.domain.interfaces.email_service import EmailService

class SendGridEmailService(EmailService):
    def __init__(self, client: SendGridClient, from_email: str, admin_email: str):
        self.client = client
        self.from_email = from_email
        self.admin_email = admin_email

    async def send_email(self, to_email: str, subject: str, content: str) -> None:
        # We can use a simple HTML template here or pass it in.
        # For now, we'll wrap the content in a nice div.
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
            <h2 style="color: #333;">Library Notification</h2>
            <p>{content}</p>
            <hr>
            <p style="font-size: 12px; color: #777;">This is an automated message from your Library System.</p>
        </div>
        """
        
        # Send email with CC to admin
        self.client.send(
            from_email=self.from_email,
            to_email=to_email,
            subject=subject,
            content_str=html_content,
            cc_email=self.admin_email
        )
        print(f"[SendGridAdapter] Email sent to {to_email} (CC: {self.admin_email})")

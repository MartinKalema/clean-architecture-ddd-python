import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content, Cc

class SendGridClient:
    def __init__(self, api_key: str):
        self.sg = sendgrid.SendGridAPIClient(api_key=api_key)

    def send(self, from_email: str, to_email: str, subject: str, content_str: str, cc_email: str = None):
        # This is a synchronous call, but we wrap it in the client.
        # The Adapter will handle async execution if needed (e.g. run_in_executor).
        
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
            return response.status_code
        except Exception as e:
            print(f"[SendGridClient] Error: {e}")
            raise e

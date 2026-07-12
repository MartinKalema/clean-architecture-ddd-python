from __future__ import annotations

from typing import TYPE_CHECKING

import sendgrid
from sendgrid.helpers.mail import Content, CustomArg, Email, Mail, To

if TYPE_CHECKING:
    from src.application.ports import ILogger


class SendGridClient:
    def __init__(
        self,
        api_key: str,
        logger: ILogger,
        request_timeout_seconds: float = 15.0,
    ):
        if (
            isinstance(request_timeout_seconds, bool)
            or request_timeout_seconds <= 0
            or request_timeout_seconds > 60
        ):
            raise ValueError(
                "SendGrid request timeout must be greater than 0 and at most 60 seconds"
            )
        self.sg = sendgrid.SendGridAPIClient(api_key=api_key)
        self.logger = logger
        self.request_timeout_seconds = float(request_timeout_seconds)

    def send(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        content_str: str,
        delivery_id: str | None = None,
    ):
        message = Mail(
            from_email=Email(from_email),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", content_str)
        )
        if delivery_id is not None:
            message.add_custom_arg(CustomArg("delivery_id", delivery_id))

        try:
            # python-http-client (used by SendGrid's SDK) forwards this timeout
            # to urllib's transport. Bounding the real socket operation avoids
            # tying up the single event-consumer loop indefinitely; an outer
            # asyncio timeout alone cannot cancel an executor thread safely.
            response = self.sg.client.mail.send.post(
                request_body=message.get(),
                timeout=self.request_timeout_seconds,
            )
            self.logger.info(f"Email sent to {to_email}. Status: {response.status_code}")
            return response.status_code
        except Exception as e:
            self.logger.error(f"SendGrid API Error: {e}", exception=e)
            raise

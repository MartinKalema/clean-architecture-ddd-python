from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import Dict, Any
from src.domain.interfaces.template_renderer import TemplateRenderer
from src.domain.value_objects.email_template import EmailTemplate
from src.domain.interfaces.logger import Logger
import os

class Jinja2TemplateRenderer:
    def __init__(self, template_dir: str, template_map: Dict[str, str], logger: Logger):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
        self.template_map = template_map
        self.logger = logger

    def render(self, template: Any, context: Dict[str, Any]) -> str:
        if isinstance(template, EmailTemplate):
            # Look up file path from config map using enum value
            template_name = self.template_map.get(template.value)
            if not template_name:
                self.logger.error(f"No template mapped for {template.value}")
                raise ValueError(f"No template mapped for {template.value}")
        else:
            template_name = str(template)
            
        try:
            jinja_template = self.env.get_template(template_name)
            return jinja_template.render(**context)
        except Exception as e:
            from src.infrastructure.exceptions.infrastructure_exceptions import TemplateRenderingException
            self.logger.error(f"Failed to render template {template_name}", exception=e)
            raise TemplateRenderingException(f"Failed to render template {template_name}: {str(e)}", original_exception=e)

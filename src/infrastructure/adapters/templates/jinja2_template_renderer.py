from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import Dict, Any
from src.domain.value_objects.email_template import EmailTemplate
import os

class Jinja2TemplateRenderer:
    def __init__(self, template_dir: str, template_map: Dict[str, str]):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
        self.template_map = template_map

    def render(self, template: Any, context: Dict[str, Any]) -> str:
        if isinstance(template, EmailTemplate):
            # Look up file path from config map using enum value
            template_name = self.template_map.get(template.value)
            if not template_name:
                raise ValueError(f"No template mapped for {template.value}")
        else:
            template_name = str(template)
            
        jinja_template = self.env.get_template(template_name)
        return jinja_template.render(**context)

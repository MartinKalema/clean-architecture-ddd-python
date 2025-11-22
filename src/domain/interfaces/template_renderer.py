from typing import Protocol, Dict, Any

class TemplateRenderer(Protocol):
    def render(self, template: Any, context: Dict[str, Any]) -> str:
        ...

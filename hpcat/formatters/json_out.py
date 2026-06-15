import json
from typing import Dict, Any

def render(data: Dict[str, Any], module: str = "") -> str:
    return json.dumps(data, indent=2)

import io
import csv
from typing import Dict, Any

def render(data: Dict[str, Any], module: str) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    
    if module == "gpus":
        writer.writerow([
            "Node", "GPU_Index", "Model", "Util_Pct", 
            "Mem_Used_MB", "Mem_Total_MB", "Temp_C", "Power_W", "Error"
        ])
        for node, node_data in sorted(data.items()):
            if "error" in node_data:
                writer.writerow([node, "", "", "", "", "", "", "", node_data["error"]])
                continue
            for gpu in node_data.get("gpus", []):
                writer.writerow([
                    node, gpu["index"], gpu["model"], gpu["util_pct"],
                    gpu["mem_used_mb"], gpu["mem_total_mb"], gpu["temp_c"], gpu["power_w"], ""
                ])
                
    return output.getvalue().strip()

from typing import Dict, Any, List, Tuple

def render(data: Dict[str, Any], module: str) -> str:
    """Translates raw dictionary data into Prometheus exposition format."""
    lines = []
    
    def add_metric(name: str, help_text: str, mtype: str, points: List[Tuple[str, float]]) -> None:
        if not points:
            return
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")
        for labels, value in points:
            lines.append(f"{name}{{{labels}}} {value}")

    if module == "gpus":
        util, mem_used, mem_tot, temp, pwr = [], [], [], [], []
        
        for node, node_data in data.items():
            if "error" in node_data:
                continue
            for gpu in node_data.get("gpus", []):
                lbl = f'node="{node}",gpu_index="{gpu["index"]}",model="{gpu["model"]}"'
                util.append((lbl, gpu["util_pct"]))
                mem_used.append((lbl, gpu["mem_used_mb"] * 1048576))  # Convert MB to Bytes
                mem_tot.append((lbl, gpu["mem_total_mb"] * 1048576))
                temp.append((lbl, gpu["temp_c"]))
                pwr.append((lbl, gpu["power_w"]))

        add_metric("hpcat_gpu_utilization_percent", "GPU Utilization %", "gauge", util)
        add_metric("hpcat_gpu_memory_used_bytes", "GPU Memory Used (Bytes)", "gauge", mem_used)
        add_metric("hpcat_gpu_memory_total_bytes", "GPU Memory Total (Bytes)", "gauge", mem_tot)
        add_metric("hpcat_gpu_temperature_celsius", "GPU Temperature (C)", "gauge", temp)
        add_metric("hpcat_gpu_power_draw_watts", "GPU Power Draw (W)", "gauge", pwr)

    return "\n".join(lines)

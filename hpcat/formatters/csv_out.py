# hpcat/formatters/csv_out.py
import io
import csv
import socket
from typing import Dict, Any

def render(data: Dict[str, Any], module: str) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    
    if module == "gpus" or module == "gpu":
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

    elif module == "cpu":
        # Get the short hostname to match the GPU node format
        node = socket.gethostname().split('.')[0]
        
        writer.writerow([
            "Node", "Model", "Architecture", "CPUs", "Sockets", 
            "Cores_Per_Socket", "Threads_Per_Core", "NUMA_Nodes",
            "Slurm_Total", "Slurm_Load", "Slurm_State", "Error"
        ])
        
        if "error" in data:
            writer.writerow([node, "", "", "", "", "", "", "", "", "", "", data["error"]])
        else:
            writer.writerow([
                node,
                data.get("model_name", ""),
                data.get("architecture", ""),
                data.get("cpu(s)", ""),
                data.get("socket(s)", ""),
                data.get("core(s)_per_socket", ""),
                data.get("thread(s)_per_core", ""),
                data.get("numa_node(s)", ""),
                data.get("slurm_cputot", ""),
                data.get("slurm_cpuload", ""),
                data.get("slurm_state", ""),
                ""
            ])
                
    return output.getvalue().strip()

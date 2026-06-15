import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple

# Import the decoupled formatters
from hpcat.formatters import json_out, csv_out, prometheus_out

SSH_TIMEOUT = 3
MAX_WORKERS = 30
NVIDIA_SMI_CMD = (
    "nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,"
    "memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits"
)

def get_gpu_nodes() -> List[str]:
    """Discover nodes with GPU GRES via Slurm."""
    try:
        result = subprocess.run(
            ['sinfo', '-N', '-h', '-o', '%n|%G'],
            capture_output=True, text=True, check=True
        )
        nodes = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            node, gres = line.split('|', 1)
            if 'gpu' in gres.lower():
                nodes.append(node.strip())
        return list(set(nodes))
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Slurm discovery failed: {e}", file=sys.stderr)
        return []

def poll_node(node: str) -> Tuple[str, Dict[str, Any]]:
    """Fetch real-time GPU metrics via SSH."""
    cmd = [
        'ssh',
        '-o', 'BatchMode=yes',
        '-o', f'ConnectTimeout={SSH_TIMEOUT}',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'LogLevel=QUIET',
        node,
        NVIDIA_SMI_CMD
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=SSH_TIMEOUT + 2)
        if result.returncode != 0:
            return node, {"error": "ssh_auth_or_smi_failed"}
        
        gpus = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = [p.strip() for p in line.split(',')]
            gpus.append({
                "index": int(parts[0]),
                "model": parts[1].replace('"', ''),
                "util_pct": float(parts[2]) if parts[2] != '[Not Supported]' else 0.0,
                "mem_used_mb": float(parts[3]),
                "mem_total_mb": float(parts[4]),
                "temp_c": float(parts[5]),
                "power_w": float(parts[6]) if parts[6] != '[Not Supported]' else 0.0
            })
        return node, {"gpus": gpus}
    except subprocess.TimeoutExpired:
        return node, {"error": "timeout"}
    except Exception as e:
        return node, {"error": str(e)}

def execute(args: Any) -> int:
    """Main execution router for the gpu subcommand."""
    target_nodes = args.nodes if args.nodes else get_gpu_nodes()
    if not target_nodes:
        print("No targets identified. Exiting.", file=sys.stderr)
        return 1

    cluster_state = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(poll_node, node): node for node in target_nodes}
        for future in as_completed(futures):
            node, node_data = future.result()
            cluster_state[node] = node_data

    # Route raw dictionary to the requested formatter
    if getattr(args, 'prometheus', False):
        print(prometheus_out.render(cluster_state, module="gpus"))
    elif getattr(args, 'csv', False):
        print(csv_out.render(cluster_state, module="gpus"))
    elif getattr(args, 'json', False):
        print(json_out.render(cluster_state, module="gpus"))
    else:
        # FIXED: Now correctly falls back to the human-readable table
        print_console(cluster_state)
        
    return 0

def print_console(data: Dict[str, Dict[str, Any]]) -> None:
    """Formats the GPU data into a clean terminal table."""
    print("=" * 95)
    print(f"{'Node':<12} | {'IDX':<3} | {'Model':<20} | {'Util':<6} | {'VRAM (GB)':<13} | {'Temp':<4} | {'Power'}")
    print("=" * 95)
    
    for node in sorted(data.keys()):
        node_data = data[node]
        if "error" in node_data:
            print(f"{node:<12} | [ ERROR: {node_data['error']} ]")
            continue
            
        for gpu in node_data.get("gpus", []):
            vram = f"{gpu['mem_used_mb']/1024:.1f}/{gpu['mem_total_mb']/1024:.1f}"
            util = f"{gpu['util_pct']:.1f}%"
            print(
                f"{node:<12} | {gpu['index']:<3} | {gpu['model']:<20} | "
                f"{util:>6} | {vram:<13} | {gpu['temp_c']:>2.0f}°C | {gpu['power_w']:>5.1f}W"
            )
    print("=" * 95)

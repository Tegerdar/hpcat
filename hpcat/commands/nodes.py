# hpcat/commands/nodes.py
import subprocess
import sys
from typing import Dict, Any

# Import the formatters
from hpcat.formatters import json_out, csv_out, prometheus_out

def get_node_stats() -> Dict[str, Any]:
    """Queries Slurm for physical vs allocated node resources."""
    cmd = ['sinfo', '-N', '-h', '-o', '%n|%T|%C|%m|%a']
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Slurm execution failed: {e}", file=sys.stderr)
        return {"error": "slurm_unreachable", "nodes": {}}

    nodes = {}
    cluster_totals = {
        "cpus_total": 0, "cpus_alloc": 0,
        "mem_total_mb": 0, "mem_alloc_mb": 0
    }

    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        
        parts = line.split('|')
        if len(parts) != 5:
            continue
            
        node_raw, state, cpu_str, mem_tot, mem_alloc = parts
        node = node_raw.strip()

        # FIXED: Prevent double-counting if a node is in multiple Slurm partitions
        if node in nodes:
            continue
        
        try:
            cpu_alloc, cpu_idle, cpu_other, cpu_tot = map(int, cpu_str.split('/'))
        except ValueError:
            continue
        
        clean_state = state.strip().replace('*', '')
        mem_tot_val = int(mem_tot) if mem_tot.isdigit() else 0
        mem_alloc_val = int(mem_alloc) if mem_alloc.isdigit() else 0

        nodes[node] = {
            "state": clean_state,
            "cpus_total": cpu_tot,
            "cpus_allocated": cpu_alloc,
            "mem_total_mb": mem_tot_val,
            "mem_allocated_mb": mem_alloc_val
        }

        if clean_state not in ['down', 'drain', 'drng', 'fail', 'maint']:
            cluster_totals["cpus_total"] += cpu_tot
            cluster_totals["cpus_alloc"] += cpu_alloc
            cluster_totals["mem_total_mb"] += mem_tot_val
            cluster_totals["mem_alloc_mb"] += mem_alloc_val

    return {"cluster": cluster_totals, "nodes": nodes}

def print_console(data: Dict[str, Any]) -> None:
    """Formats the node data into a clean terminal table."""
    if "error" in data:
        print(f"Error: {data['error']}", file=sys.stderr)
        return

    print("=" * 75)
    print(f"{'Node':<15} | {'State':<12} | {'CPUs (Alloc/Tot)':<18} | {'RAM (Alloc/Tot GB)'}")
    print("=" * 75)

    for node, stats in sorted(data['nodes'].items()):
        cpu_str = f"{stats['cpus_allocated']:>3} / {stats['cpus_total']:<3}"
        # Convert MB to GB for readability
        ram_str = f"{stats['mem_allocated_mb']/1024:>5.1f} / {stats['mem_total_mb']/1024:<5.1f}"
        print(f"{node:<15} | {stats['state']:<12} | {cpu_str:<18} | {ram_str}")
    
    print("-" * 75)
    
    ct = data['cluster']
    c_cpu_str = f"{ct['cpus_alloc']:>3} / {ct['cpus_total']:<3}"
    c_ram_str = f"{ct['mem_alloc_mb']/1024:>5.1f} / {ct['mem_total_mb']/1024:<5.1f}"
    print(f"{'CLUSTER TOTAL':<15} | {'ACTIVE':<12} | {c_cpu_str:<18} | {c_ram_str}")
    print("=" * 75)

def execute(args: Any) -> int:
    """Entry point for the nodes subcommand."""
    data = get_node_stats()
    
    if getattr(args, 'prometheus', False):
        print(prometheus_out.render(data, module="nodes"))
    elif getattr(args, 'csv', False):
        print(csv_out.render(data, module="nodes"))
    elif getattr(args, 'json', False):
        print(json_out.render(data, module="nodes"))
    else:
        print_console(data)
        
    return 0 if "error" not in data else 1

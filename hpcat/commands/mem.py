# hpcat/commands/mem.py
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple

# Import the decoupled formatters
from hpcat.formatters import json_out, csv_out, prometheus_out
# Import security utilities
from hpcat.security import (
    validate_node_name,
    validate_node_list,
    build_ssh_command,
    get_safe_error_message,
    MAX_WORKERS_DEFAULT,
    SSH_TIMEOUT_DEFAULT,
)

SSH_TIMEOUT = SSH_TIMEOUT_DEFAULT
MAX_WORKERS = MAX_WORKERS_DEFAULT

def get_mem_nodes() -> List[str]:
    """Discover all compute nodes via Slurm."""
    try:
        # -N (Node format), -h (no header), -o '%n' (node name only)
        result = subprocess.run(
            ['sinfo', '-N', '-h', '-o', '%n'],
            capture_output=True, text=True, check=True,
            timeout=10  # Added timeout
        )
        nodes = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                try:
                    validated_node = validate_node_name(line.strip())
                    nodes.append(validated_node)
                except ValueError:
                    # Skip invalid node names
                    continue
        return list(set(nodes))
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Slurm discovery failed: {get_safe_error_message(e, 'Slurm discovery')}", file=sys.stderr)
        return []
    except subprocess.TimeoutExpired:
        print("Slurm discovery timed out", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Slurm discovery error: {get_safe_error_message(e, 'Slurm discovery')}", file=sys.stderr)
        return []

def poll_node(node: str, extended: bool) -> Tuple[str, Dict[str, Any]]:
    """Fetch real-time Memory metrics via SSH and local Slurm query."""
    hw_data = {}
    slurm_data = {}

    # Validate node name
    try:
        validated_node = validate_node_name(node)
    except ValueError as e:
        return node, {"error": str(e)}

    # 1. SSH to get OS-level memory data via /proc/meminfo
    try:
        cmd = build_ssh_command(
            validated_node,
            'cat /proc/meminfo',
            timeout=SSH_TIMEOUT,
            batch_mode=True,
            quiet=True
        )
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=SSH_TIMEOUT + 2)
        if result.returncode != 0:
            hw_data = {"error": "ssh_auth_or_meminfo_failed"}
        else:
            common_keys = {'MemTotal', 'MemFree', 'MemAvailable', 'Buffers', 'Cached', 'SwapTotal', 'SwapFree'}
            
            for line in result.stdout.strip().split('\n'):
                if ':' not in line:
                    continue
                key, value_str = line.split(':', 1)
                key = key.strip()
                
                if extended or key in common_keys:
                    # Parse the integer value (which is usually in kB)
                    val_parts = value_str.strip().split()
                    if val_parts:
                        try:
                            # Convert kB to MB for easier baseline readability
                            mb_val = int(val_parts[0]) / 1024
                            hw_data[f"os_{key.lower()}_mb"] = round(mb_val, 2)
                        except ValueError:
                            hw_data[f"os_{key.lower()}"] = value_str.strip()
                            
    except subprocess.TimeoutExpired:
        hw_data = {"error": "timeout"}
    except Exception as e:
        hw_data = {"error": get_safe_error_message(e, 'Memory hardware polling')}

    # 2. Query Slurm state for this node (runs locally on the execution node)
    try:
        sctrl_result = subprocess.run(
            ['scontrol', 'show', 'node', validated_node],
            capture_output=True, 
            text=True,
            timeout=10
        )
        if sctrl_result.returncode == 0:
            target_keys = {'State', 'RealMemory', 'AllocMem', 'FreeMem'}
            for word in sctrl_result.stdout.split():
                if '=' in word:
                    key, value = word.split('=', 1)
                    if key in target_keys:
                        # Slurm memory values are typically in MB natively
                        slurm_data[f"slurm_{key.lower()}"] = value
        else:
            slurm_data = {"slurm_status": "Not in Slurm"}
    except subprocess.TimeoutExpired:
        slurm_data = {"slurm_error": "timeout"}
    except Exception as e:
        slurm_data = {"slurm_error": get_safe_error_message(e, 'Slurm query')}

    combined_data = {**hw_data, **slurm_data}
    return node, combined_data

def execute(args: Any) -> int:
    """Main execution router for the mem subcommand."""
    try:
        # Validate user-provided nodes if specified
        if args.nodes:
            try:
                target_nodes = validate_node_list(args.nodes)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1
        else:
            target_nodes = get_mem_nodes()
    except Exception as e:
        print(f"Error validating nodes: {get_safe_error_message(e, 'Node validation')}", file=sys.stderr)
        return 1
    
    if not target_nodes:
        print("No targets identified. Exiting.", file=sys.stderr)
        return 1

    extended = getattr(args, 'extended', False)
    cluster_state = {}
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(poll_node, node, extended): node for node in target_nodes}
        for future in as_completed(futures):
            node, node_data = future.result()
            cluster_state[node] = node_data

    # Route raw dictionary to the requested formatter
    if getattr(args, 'prometheus', False):
        print(prometheus_out.render(cluster_state, module="memory"))
    elif getattr(args, 'csv', False):
        print(csv_out.render(cluster_state, module="memory"))
    elif getattr(args, 'json', False):
        print(json_out.render(cluster_state, module="memory"))
    else:
        print_console(cluster_state, extended)
        
    return 0

def print_console(data: Dict[str, Dict[str, Any]], extended: bool = False) -> None:
    """Formats the memory data into a clean terminal table."""
    print("=" * 110)
    print(f"{'Node':<12} | {'State':<12} | {'OS Total':<10} | {'OS Avail':<10} | {'Slurm Real':<10} | {'Slurm Alloc':<11} | {'Slurm Free'}")
    print("=" * 110)
    
    for node in sorted(data.keys()):
        node_data = data[node]
        
        if "error" in node_data and "slurm_error" in node_data:
            print(f"{node:<12} | [ ERROR: {node_data.get('error', 'Unknown Error')} ]")
            continue
            
        state = node_data.get("slurm_state", "UNKNOWN")[:12]
        
        if "error" in node_data:
            os_total = f"ERR: {node_data['error']}"[:10]
            os_avail = "-"
        else:
            # Convert OS MB to GB for the display table
            total_mb = node_data.get("os_memtotal_mb", 0)
            avail_mb = node_data.get("os_memavailable_mb", 0)
            os_total = f"{total_mb / 1024:.1f}G" if total_mb else "-"
            os_avail = f"{avail_mb / 1024:.1f}G" if avail_mb else "-"
            
        # Slurm parameters (Native MB parsed as GB for display)
        try:
            slurm_real = f"{float(node_data.get('slurm_realmemory', 0)) / 1024:.1f}G"
            slurm_alloc = f"{float(node_data.get('slurm_allocmem', 0)) / 1024:.1f}G"
            slurm_free = f"{float(node_data.get('slurm_freemem', 0)) / 1024:.1f}G"
        except ValueError:
            slurm_real = node_data.get("slurm_realmemory", "-")
            slurm_alloc = node_data.get("slurm_allocmem", "-")
            slurm_free = node_data.get("slurm_freemem", "-")
        
        print(f"{node:<12} | {state:<12} | {os_total:>10} | {os_avail:>10} | {slurm_real:>10} | {slurm_alloc:>11} | {slurm_free:>10}")
        
    print("=" * 110)

    if extended:
        print("\n[ Extended Parameters ]")
        for node in sorted(data.keys()):
            node_data = data[node]
            print(f"\n--- {node} ---")
            for key, value in node_data.items():
                print(f"  {key:<35} : {value}")

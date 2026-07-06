# hpcat/commands/cpu.py
import subprocess
import json
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

def get_cpu_nodes() -> List[str]:
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
    """Fetch real-time CPU metrics via SSH and local Slurm query."""
    hw_data = {}
    slurm_data = {}

    # Validate node name
    try:
        validated_node = validate_node_name(node)
    except ValueError as e:
        return node, {"error": str(e)}

    # 1. SSH to get lscpu hardware data
    try:
        cmd = build_ssh_command(
            validated_node,
            'lscpu -J',
            timeout=SSH_TIMEOUT,
            batch_mode=True,
            quiet=True
        )
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=SSH_TIMEOUT + 2)
        if result.returncode != 0:
            hw_data = {"error": "ssh_auth_or_lscpu_failed"}
        else:
            lscpu_data = json.loads(result.stdout)
            common_keys = {
                'model_name', 'architecture', 'cpu(s)', 'thread(s)_per_core',
                'core(s)_per_socket', 'socket(s)', 'numa_node(s)'
            }
            
            for item in lscpu_data.get('lscpu', []):
                field = item.get('field', '').replace(':', '').strip().lower().replace(' ', '_').replace('-', '_')
                if extended or field in common_keys:
                    hw_data[field] = item.get('data')
    except subprocess.TimeoutExpired:
        hw_data = {"error": "timeout"}
    except json.JSONDecodeError:
        hw_data = {"error": "lscpu_parse_failed"}
    except Exception as e:
        hw_data = {"error": get_safe_error_message(e, 'CPU hardware polling')}

    # 2. Query Slurm state for this node (runs locally on the execution node)
    try:
        sctrl_result = subprocess.run(
            ['scontrol', 'show', 'node', validated_node], 
            capture_output=True, 
            text=True,
            timeout=10
        )
        if sctrl_result.returncode == 0:
            target_keys = {'State', 'CPUTot', 'CPULoad', 'AllocCPUs', 'IdleCPUs'}
            for word in sctrl_result.stdout.split():
                if '=' in word:
                    key, value = word.split('=', 1)
                    if key in target_keys:
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
    """Main execution router for the cpu subcommand."""
    try:
        # Validate user-provided nodes if specified
        if args.nodes:
            try:
                target_nodes = validate_node_list(args.nodes)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1
        else:
            target_nodes = get_cpu_nodes()
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
        print(prometheus_out.render(cluster_state, module="cpu"))
    elif getattr(args, 'csv', False):
        print(csv_out.render(cluster_state, module="cpu"))
    elif getattr(args, 'json', False):
        print(json_out.render(cluster_state, module="cpu"))
    else:
        print_console(cluster_state, extended)
        
    return 0

def print_console(data: Dict[str, Dict[str, Any]], extended: bool = False) -> None:
    """Formats the CPU data into a clean terminal table."""
    print("=" * 115)
    print(f"{'Node':<12} | {'State':<12} | {'CPU Model':<30} | {'CPUs (A/I/T)':<14} | {'Load':<6} | {'Sockets':<7} | {'NUMA':<4}")
    print("=" * 115)
    
    for node in sorted(data.keys()):
        node_data = data[node]
        
        if "error" in node_data and "slurm_error" in node_data:
            print(f"{node:<12} | [ ERROR: {node_data.get('error', 'Unknown Error')} ]")
            continue
            
        state = node_data.get("slurm_state", "UNKNOWN")[:12]
        
        if "error" in node_data:
            model = f"SSH ERR: {node_data['error']}"[:30]
            cpus_ait = "-/-/-"
            load = "-"
            sockets = "-"
            numa = "-"
        else:
            model = str(node_data.get("model_name", "Unknown"))[:30]
            sockets = str(node_data.get("socket(s)", "-"))
            numa = str(node_data.get("numa_node(s)", "-"))
            
            alloc = node_data.get("slurm_alloccpus", "-")
            idle = node_data.get("slurm_idlecpus", "-")
            total = node_data.get("slurm_cputot", node_data.get("cpu(s)", "-"))
            cpus_ait = f"{alloc}/{idle}/{total}"
            load = str(node_data.get("slurm_cpuload", "-"))
        
        print(f"{node:<12} | {state:<12} | {model:<30} | {cpus_ait:<14} | {load:<6} | {sockets:<7} | {numa:<4}")
        
    print("=" * 115)

    if extended:
        print("\n[ Extended Parameters ]")
        for node in sorted(data.keys()):
            node_data = data[node]
            print(f"\n--- {node} ---")
            for key, value in node_data.items():
                print(f"  {key:<35} : {value}")

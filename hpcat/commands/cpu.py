# hpcat/commands/cpu.py
import subprocess
import json
import sys
import socket
from typing import Dict, Any

from hpcat.formatters import json_out, csv_out, prometheus_out

def get_cpu_hardware_info(extended: bool = False) -> Dict[str, Any]:
    """Queries the OS for CPU parameters using lscpu."""
    try:
        result = subprocess.run(['lscpu', '-J'], capture_output=True, text=True, check=True)
        lscpu_data = json.loads(result.stdout)
        
        # Ultra-lean allowlist for standard HPC monitoring (Cache removed)
        common_keys = {
            'model_name', 'architecture', 'cpu(s)', 'thread(s)_per_core',
            'core(s)_per_socket', 'socket(s)', 'numa_node(s)'
        }
        
        cpu_details = {}
        for item in lscpu_data.get('lscpu', []):
            field = item.get('field', '').replace(':', '').strip().lower().replace(' ', '_').replace('-', '_')
            
            # If extended is True, grab everything. Otherwise, filter strictly.
            if extended or field in common_keys:
                cpu_details[field] = item.get('data')
                
        return cpu_details
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Hardware execution failed: {e}", file=sys.stderr)
        return {"error": "cpu_discovery_failed"}

def get_slurm_cpu_state() -> Dict[str, Any]:
    """Queries Slurm for the local node's CPU allocation and load state."""
    try:
        hostname = socket.gethostname().split('.')[0]
        result = subprocess.run(['scontrol', 'show', 'node', hostname], capture_output=True, text=True)
        
        if result.returncode != 0:
            return {"slurm_status": "Node not found in Slurm"}

        slurm_data = {}
        target_keys = {'State', 'CPUTot', 'CPULoad', 'AllocCPUs', 'IdleCPUs'}
        
        for word in result.stdout.split():
            if '=' in word:
                key, value = word.split('=', 1)
                if key in target_keys:
                    slurm_data[f"slurm_{key.lower()}"] = value
                    
        return slurm_data
    except FileNotFoundError:
        return {"slurm_status": "scontrol command not found"}
    except Exception as e:
        return {"slurm_error": str(e)}

def print_cpu_console(hw_data: Dict[str, Any], slurm_data: Dict[str, Any], extended: bool = False) -> None:
    """Formats the combined CPU and Slurm data into a clean terminal view."""
    if "error" in hw_data:
        print(f"Error: {hw_data['error']}", file=sys.stderr)
        return

    print("=" * 60)
    print(f"{'CPU HARDWARE & SLURM TELEMETRY':^60}")
    print("=" * 60)
    
    print("\n[ Hardware Specification ]")
    # Consolidated core hardware metrics including NUMA
    key_fields = ['model_name', 'architecture', 'cpu(s)', 'socket(s)', 'core(s)_per_socket', 'thread(s)_per_core', 'numa_node(s)']
    for key in key_fields:
        if key in hw_data:
            print(f"{key.replace('_', ' ').title():<25} : {hw_data[key]}")

    print("\n[ Slurm Node State ]")
    if not slurm_data or "slurm_status" in slurm_data or "slurm_error" in slurm_data:
        err = slurm_data.get("slurm_status", slurm_data.get("slurm_error", "Unknown Slurm state"))
        print(f"{'Status':<25} : {err}")
    else:
        for key, value in slurm_data.items():
            clean_key = key.replace('slurm_', '').replace('_', ' ').title()
            print(f"{clean_key:<25} : {value}")
    
    # Append the massive block of raw data if the user passed -e
    if extended:
        print("\n[ Extended Parameters ]")
        printed_keys = set(key_fields)
        for key, value in hw_data.items():
            if key not in printed_keys and value:
                print(f"{key:<38} : {value}")

    print("=" * 60)

def execute(args: Any) -> int:
    """Entry point for the cpu subcommand."""
    extended = getattr(args, 'extended', False)
    
    hw_data = get_cpu_hardware_info(extended)
    slurm_data = get_slurm_cpu_state()
    
    combined_data = {**hw_data, **slurm_data}
    
    if getattr(args, 'prometheus', False):
        print(prometheus_out.render(combined_data, module="cpu"))
    elif getattr(args, 'csv', False):
        print(csv_out.render(combined_data, module="cpu"))
    elif getattr(args, 'json', False):
        print(json_out.render(combined_data, module="cpu"))
    else:
        print_cpu_console(hw_data, slurm_data, extended)
        
    return 0 if "error" not in combined_data else 1

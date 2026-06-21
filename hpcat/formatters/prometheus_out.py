# hpcat/formatters/prometheus_out.py
import socket
from typing import Dict, Any, List, Tuple

def render(data: Dict[str, Any], module: str) -> str:
    """Translates raw dictionary data into Prometheus exposition format."""
    lines: List[str] = []

    def add_metric(name: str, help_text: str, mtype: str, points: List[Tuple[str, float]]) -> None:
        if not points:
            return
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")
        for labels, value in points:
            lines.append(f"{name}{{{labels}}} {value}")

    # GPU section (unchanged logic, per-node metrics)
    if module == "gpus" or module == "gpu":
        util, mem_used, mem_tot, temp, pwr = [], [], [], [], []

        for node, node_data in data.items():
            if "error" in node_data:
                continue
            for gpu in node_data.get("gpus", []):
                lbl = f'node="{node}",gpu_index="{gpu["index"]}",model="{gpu["model"]}"'
                util.append((lbl, gpu["util_pct"]))
                mem_used.append((lbl, gpu["mem_used_mb"] * 1048576))  # MB -> Bytes
                mem_tot.append((lbl, gpu["mem_total_mb"] * 1048576))
                temp.append((lbl, gpu["temp_c"]))
                pwr.append((lbl, gpu["power_w"]))

        add_metric("hpcat_gpu_utilization_percent", "GPU Utilization %", "gauge", util)
        add_metric("hpcat_gpu_memory_used_bytes", "GPU Memory Used (Bytes)", "gauge", mem_used)
        add_metric("hpcat_gpu_memory_total_bytes", "GPU Memory Total (Bytes)", "gauge", mem_tot)
        add_metric("hpcat_gpu_temperature_celsius", "GPU Temperature (C)", "gauge", temp)
        add_metric("hpcat_gpu_power_draw_watts", "GPU Power Draw (W)", "gauge", pwr)

    # CPU section: export per-node metrics (do not assume local hostname)
    elif module in ("cpu", "cpus"):
        cores: List[Tuple[str, float]] = []
        sockets: List[Tuple[str, float]] = []
        slurm_total: List[Tuple[str, float]] = []
        slurm_load: List[Tuple[str, float]] = []

        def to_float(val: Any, default: float = 0.0) -> float:
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        for node, node_data in data.items():
            if "error" in node_data:
                continue
            model = str(node_data.get("model_name", "unknown")).replace('"', '')
            lbl = f'node="{node}",model="{model}"'
            cores.append((lbl, to_float(node_data.get("cpu(s)"))))
            sockets.append((lbl, to_float(node_data.get("socket(s)"))))

            if "slurm_cputot" in node_data:
                slurm_total.append((lbl, to_float(node_data.get("slurm_cputot"))))
            if "slurm_cpuload" in node_data:
                slurm_load.append((lbl, to_float(node_data.get("slurm_cpuload"))))

        add_metric("hpcat_cpu_cores_total", "Total OS CPU Cores", "gauge", cores)
        add_metric("hpcat_cpu_sockets_total", "Total CPU Sockets", "gauge", sockets)
        add_metric("hpcat_slurm_cpu_total", "Total CPUs allocated to Slurm", "gauge", slurm_total)
        add_metric("hpcat_slurm_cpu_load", "Current Slurm CPU Load", "gauge", slurm_load)

    # Memory section: export OS and Slurm memory metrics per-node (MB -> bytes)
    elif module in ("memory", "mem"):
        os_total: List[Tuple[str, float]] = []
        os_avail: List[Tuple[str, float]] = []
        os_free: List[Tuple[str, float]] = []
        buffers: List[Tuple[str, float]] = []
        cached: List[Tuple[str, float]] = []
        swap_tot: List[Tuple[str, float]] = []
        swap_free: List[Tuple[str, float]] = []
        slurm_real: List[Tuple[str, float]] = []
        slurm_alloc: List[Tuple[str, float]] = []
        slurm_free: List[Tuple[str, float]] = []

        def mb_to_bytes(v: Any) -> float:
            try:
                return float(v) * 1024.0 * 1024.0
            except (TypeError, ValueError):
                return 0.0

        for node, node_data in data.items():
            if "error" in node_data:
                continue
            lbl = f'node="{node}"'
            # keys populated by mem.poll_node: os_<Key>_mb
            os_total.append((lbl, mb_to_bytes(node_data.get("os_memtotal_mb"))))
            os_avail.append((lbl, mb_to_bytes(node_data.get("os_memavailable_mb"))))
            os_free.append((lbl, mb_to_bytes(node_data.get("os_memfree_mb"))))
            buffers.append((lbl, mb_to_bytes(node_data.get("os_buffers_mb"))))
            cached.append((lbl, mb_to_bytes(node_data.get("os_cached_mb"))))
            swap_tot.append((lbl, mb_to_bytes(node_data.get("os_swaptotal_mb"))))
            swap_free.append((lbl, mb_to_bytes(node_data.get("os_swapfree_mb"))))

            # Slurm keys are MB already: slurm_realmemory, slurm_allocmem, slurm_freemem
            slurm_real.append((lbl, mb_to_bytes(node_data.get("slurm_realmemory"))))
            slurm_alloc.append((lbl, mb_to_bytes(node_data.get("slurm_allocmem"))))
            slurm_free.append((lbl, mb_to_bytes(node_data.get("slurm_freemem"))))

        add_metric("hpcat_os_memory_total_bytes", "OS Memory Total (bytes)", "gauge", os_total)
        add_metric("hpcat_os_memory_available_bytes", "OS Memory Available (bytes)", "gauge", os_avail)
        add_metric("hpcat_os_memory_free_bytes", "OS Memory Free (bytes)", "gauge", os_free)
        add_metric("hpcat_os_memory_buffers_bytes", "OS Memory Buffers (bytes)", "gauge", buffers)
        add_metric("hpcat_os_memory_cached_bytes", "OS Memory Cached (bytes)", "gauge", cached)
        add_metric("hpcat_os_swap_total_bytes", "OS Swap Total (bytes)", "gauge", swap_tot)
        add_metric("hpcat_os_swap_free_bytes", "OS Swap Free (bytes)", "gauge", swap_free)
        add_metric("hpcat_slurm_memory_real_bytes", "Slurm RealMemory (bytes)", "gauge", slurm_real)
        add_metric("hpcat_slurm_memory_alloc_bytes", "Slurm AllocMem (bytes)", "gauge", slurm_alloc)
        add_metric("hpcat_slurm_memory_free_bytes", "Slurm FreeMem (bytes)", "gauge", slurm_free)

    return "\n".join(lines)

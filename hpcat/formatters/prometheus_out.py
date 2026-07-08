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

    # Network section: per-port IB/RoCE link state + key ethtool error counters
    elif module == "network":
        link_up: List[Tuple[str, float]] = []
        out_of_buffer: List[Tuple[str, float]] = []
        crc_errors: List[Tuple[str, float]] = []
        symbol_errors: List[Tuple[str, float]] = []
        rx_discards: List[Tuple[str, float]] = []
        tx_discards: List[Tuple[str, float]] = []
        link_down_events: List[Tuple[str, float]] = []
        pause_active: List[Tuple[str, float]] = []

        def to_float(val: Any, default: float = 0.0) -> float:
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        for node, node_data in data.items():
            if "error" in node_data:
                continue
            netdevs = node_data.get("netdevs", {})
            for p in node_data.get("ports", []):
                nd = p["netdev"]
                lbl = f'node="{node}",device="{p["device"]}",netdev="{nd}",link_layer="{p["link_layer"]}"'
                link_up.append((lbl, 1.0 if p["state"] == "ACTIVE" else 0.0))

                stats = netdevs.get(nd, {}).get("stats", {}) if nd != "-" else {}
                if not stats:
                    continue
                out_of_buffer.append((lbl, to_float(stats.get("rx_out_of_buffer"))))
                crc_errors.append((lbl, to_float(stats.get("rx_crc_errors_phy"))))
                symbol_errors.append((lbl, to_float(stats.get("rx_symbol_err_phy"))))
                rx_discards.append((lbl, to_float(stats.get("rx_discards_phy"))))
                tx_discards.append((lbl, to_float(stats.get("tx_discards_phy"))))
                link_down_events.append((lbl, to_float(stats.get("link_down_events_phy"))))
                pause_on = to_float(stats.get("rx_pause_ctrl_phy")) > 0 or to_float(stats.get("tx_pause_ctrl_phy")) > 0
                pause_active.append((lbl, 1.0 if pause_on else 0.0))

        add_metric("hpcat_ib_port_link_up", "1 if port state is ACTIVE, else 0", "gauge", link_up)
        add_metric("hpcat_net_rx_out_of_buffer_total", "RX ring buffer overflow count", "counter", out_of_buffer)
        add_metric("hpcat_net_rx_crc_errors_phy_total", "PHY-level RX CRC errors", "counter", crc_errors)
        add_metric("hpcat_net_rx_symbol_errors_phy_total", "PHY-level RX symbol errors", "counter", symbol_errors)
        add_metric("hpcat_net_rx_discards_phy_total", "PHY-level RX discards", "counter", rx_discards)
        add_metric("hpcat_net_tx_discards_phy_total", "PHY-level TX discards", "counter", tx_discards)
        add_metric("hpcat_net_link_down_events_phy_total", "PHY-level link down event count", "counter", link_down_events)
        add_metric("hpcat_net_pause_frames_active", "1 if RX or TX pause frames observed, else 0", "gauge", pause_active)

    # Storage section: mount-level usage plus BeeGFS/Lustre target free%
    elif module == "storage":
        mount_use_pct: List[Tuple[str, float]] = []
        mount_avail_bytes: List[Tuple[str, float]] = []
        beegfs_free_pct: List[Tuple[str, float]] = []
        lustre_use_pct: List[Tuple[str, float]] = []

        def to_float(val: Any, default: float = 0.0) -> float:
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        for node, node_data in data.items():
            if "error" in node_data:
                continue

            for m in node_data.get("mounts", []):
                lbl = f'node="{node}",mountpoint="{m["mountpoint"]}",fstype="{m["fstype"]}"'
                pcent = str(m.get("pcent", "")).rstrip('%')
                mount_use_pct.append((lbl, to_float(pcent, -1.0)))
                try:
                    avail_bytes = int(m["avail_1k"]) * 1024.0
                    mount_avail_bytes.append((lbl, avail_bytes))
                except (ValueError, KeyError):
                    pass

            beegfs = node_data.get("beegfs", {})
            for kind, rows in (("meta", beegfs.get("meta", [])), ("storage", beegfs.get("storage", []))):
                for r in rows:
                    if "target_id" not in r:
                        continue
                    lbl = f'node="{node}",target_id="{r["target_id"]}",kind="{kind}",pool="{r["pool"]}"'
                    beegfs_free_pct.append((lbl, to_float(r.get("free_pct"))))

            for r in node_data.get("lustre", []):
                if "target" not in r:
                    continue
                lbl = f'node="{node}",target="{r["target"]}"'
                lustre_use_pct.append((lbl, to_float(r.get("use_pct"))))

        add_metric("hpcat_storage_mount_use_percent", "Filesystem use percentage (df)", "gauge", mount_use_pct)
        add_metric("hpcat_storage_mount_available_bytes", "Filesystem available space (bytes)", "gauge", mount_avail_bytes)
        add_metric("hpcat_beegfs_target_free_percent", "BeeGFS target free space percentage", "gauge", beegfs_free_pct)
        add_metric("hpcat_lustre_target_use_percent", "Lustre target (MDT/OST) use percentage", "gauge", lustre_use_pct)

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

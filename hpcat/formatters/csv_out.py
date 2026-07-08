# hpcat/formatters/csv_out.py
import io
import csv
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
        writer.writerow([
            "Node", "Model", "Architecture", "CPUs", "Sockets", 
            "Cores_Per_Socket", "Threads_Per_Core", "NUMA_Nodes",
            "Slurm_Total", "Slurm_Load", "Slurm_State", "Error"
        ])

        for node, node_data in sorted(data.items()):
            if "error" in node_data:
                writer.writerow([node, "", "", "", "", "", "", "", "", "", "", node_data["error"]])
                continue

            writer.writerow([
                node,
                node_data.get("model_name", ""),
                node_data.get("architecture", ""),
                node_data.get("cpu(s)", ""),
                node_data.get("socket(s)", ""),
                node_data.get("core(s)_per_socket", ""),
                node_data.get("thread(s)_per_core", ""),
                node_data.get("numa_node(s)", ""),
                node_data.get("slurm_cputot", ""),
                node_data.get("slurm_cpuload", ""),
                node_data.get("slurm_state", ""),
                ""
            ])

    elif module == "network":
        writer.writerow([
            "Node", "Device", "Netdev", "Link_State", "Phys_State", "Link_Layer", "Rate",
            "RX_Out_Of_Buffer", "RX_CRC_Errors_Phy", "RX_Symbol_Err_Phy",
            "RX_Discards_Phy", "TX_Discards_Phy", "RX_Pause_Ctrl_Phy", "TX_Pause_Ctrl_Phy",
            "Link_Down_Events_Phy", "Error"
        ])

        for node, node_data in sorted(data.items()):
            if "error" in node_data:
                writer.writerow([node] + [""] * 14 + [node_data["error"]])
                continue

            ports = node_data.get("ports", [])
            netdevs = node_data.get("netdevs", {})

            if not ports:
                writer.writerow([node] + [""] * 14 + ["no_ib_or_roce_devices"])
                continue

            for p in ports:
                nd = p["netdev"]
                stats = netdevs.get(nd, {}).get("stats", {}) if nd != "-" else {}
                writer.writerow([
                    node, p["device"], nd, p["state"], p["phys_state"], p["link_layer"], p["rate"],
                    stats.get("rx_out_of_buffer", ""),
                    stats.get("rx_crc_errors_phy", ""),
                    stats.get("rx_symbol_err_phy", ""),
                    stats.get("rx_discards_phy", ""),
                    stats.get("tx_discards_phy", ""),
                    stats.get("rx_pause_ctrl_phy", ""),
                    stats.get("tx_pause_ctrl_phy", ""),
                    stats.get("link_down_events_phy", ""),
                    ""
                ])

    elif module == "memory" or module == "mem":
        writer.writerow([
            "Node", "OS_MemTotal_MB", "OS_MemAvailable_MB", "OS_MemFree_MB", "Buffers_MB", "Cached_MB",
            "SwapTotal_MB", "SwapFree_MB", "Slurm_RealMemory_MB", "Slurm_AllocMem_MB", "Slurm_FreeMem_MB", "Error"
        ])

        for node, node_data in sorted(data.items()):
            if "error" in node_data:
                writer.writerow([node, "", "", "", "", "", "", "", "", "", "", node_data["error"]])
                continue

            writer.writerow([
                node,
                node_data.get("os_memtotal_mb", ""),
                node_data.get("os_memavailable_mb", ""),
                node_data.get("os_memfree_mb", ""),
                node_data.get("os_buffers_mb", ""),
                node_data.get("os_cached_mb", ""),
                node_data.get("os_swaptotal_mb", ""),
                node_data.get("os_swapfree_mb", ""),
                node_data.get("slurm_realmemory", ""),
                node_data.get("slurm_allocmem", ""),
                node_data.get("slurm_freemem", ""),
                ""
            ])

    return output.getvalue().strip()

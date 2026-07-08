# hpcat

HPC Administration & Telemetry Tool

A lightweight Python CLI for querying hardware metrics in Slurm-managed HPC clusters.

## Features

- **GPU Telemetry**: Real-time GPU metrics (utilization, memory, temperature, power) gathered via SSH and nvidia-smi on GPU nodes
- **CPU State**: OS-level CPU information (via lscpu) plus Slurm per-node CPU allocation and load
- **Memory Telemetry**: OS memory details (from /proc/meminfo) and Slurm memory allocation/state
- **Network Telemetry**: InfiniBand/RoCE port state and NIC error counters (via sysfs and ethtool), with optional delta mode to track counter drift between runs
- **Storage Telemetry**: Filesystem usage (via df) plus BeeGFS/Lustre target-level capacity detail when those client tools are present
- **Flexible Output**: Human-readable tables (default), JSON, CSV, or Prometheus OpenMetrics formats
- **Parallel Discovery**: Efficient batch polling across nodes with configurable concurrency

## Installation

```bash
pip install hpcat
```

The package installs a `hpcat` console script (entry point: `hpcat.cli:main`).

## Usage

General form:
```bash
hpcat <subcommand> [OPTIONS]
```

Global formatting options are available for all subcommands:
- `-j`, `--json`        Output in machine-readable JSON
- `-c`, `--csv`         Output in flattened CSV format
- `-p`, `--prometheus`  Output in Prometheus OpenMetrics format

Examples

### GPU Metrics
Query GPU status across all GPU nodes discovered via Slurm:
```bash
hpcat gpu
```

Probe a specific list of nodes (overrides Slurm discovery):
```bash
hpcat gpu -n node01 node02 node03
```

### CPU State
Show CPU hardware details and Slurm CPU allocation:
```bash
hpcat cpu
```

Include exhaustive CPU parameters:
```bash
hpcat cpu -e
```

Probe specific nodes:
```bash
hpcat cpu -n node01 node02
```

### Memory Telemetry
Show OS and Slurm memory metrics:
```bash
hpcat mem
```

Probe specific nodes:
```bash
hpcat mem -n node01 node02
```

### Network Telemetry
Show InfiniBand/RoCE port state and key NIC error counters (link errors, buffer drops, pause frames):
```bash
hpcat network
```

Include full per-netdev counters and interface details:
```bash
hpcat network -e
```

Show counter change since the last `network` run (snapshot-based; the first run establishes the baseline, subsequent runs report the delta and flag anything that moved):
```bash
hpcat network -d
```

Probe specific nodes:
```bash
hpcat network -n node01 node02
```

### Storage Telemetry
Show filesystem usage across all mounts, plus BeeGFS/Lustre target-level free space when `beegfs-df` or `lfs` are available on the node:
```bash
hpcat storage
```

Include small/system mounts and full per-target detail (by default, mounts under 3G and uniform-looking Lustre OST groups are collapsed for readability):
```bash
hpcat storage -e
```

Probe specific nodes:
```bash
hpcat storage -n node01 node02
```

### Output Format Examples
Append a format flag to any command:
```bash
hpcat gpu -j        # JSON
hpcat gpu -c        # CSV
hpcat gpu -p        # Prometheus (OpenMetrics)
hpcat cpu -e -j     # Extended CPU info in JSON
hpcat network -d -j # Network delta, JSON
```

Note: Prometheus output is emitted in text exposition format suitable for scraping or pushing into a textfile collector.

## Requirements

- Python >= 3.9
- `ssh` (for remote polling on cluster nodes)
- Slurm utilities available on the execution host:
  - `sinfo` (used for node discovery)
  - `scontrol` (used to query per-node Slurm state)
- On target nodes:
  - `nvidia-smi` for GPU telemetry (if GPUs are present)
  - `lscpu` for CPU hardware queries (for the `cpu` subcommand)
  - `ethtool` for NIC error counters (for the `network` subcommand); sysfs (`/sys/class/infiniband`, `/sys/class/net`) is used for link state and requires no additional tooling
  - `df` for filesystem usage (for the `storage` subcommand); `beegfs-df` and/or `lfs` are used automatically if installed, but are not required
- Network reachability / SSH key setup so the execution host can SSH into compute nodes (BatchMode=no/keys)

All remote queries are read-only and do not require root or sudo on target nodes.

If Slurm discovery fails or required utilities are missing, hpcat will print an error and fall back to user-supplied node lists when possible.

## Delta snapshots (network -d)

`hpcat network -d` saves a snapshot after each run to `$XDG_CACHE_HOME/hpcat/network_snapshot.json` (or `~/.cache/hpcat/` if `XDG_CACHE_HOME` is unset). Each run compares against the previous snapshot on the same execution host; there is no shared state across different hosts or users. Counter resets (e.g. after a driver reload) are reported as `reset` rather than a misleading negative delta.

## Exit codes

- `0` — success
- non-zero — failure or no targets identified (examples: 1 for no targets, 130 for keyboard interrupt)

## Contributing

Bug reports, feature requests, and patches are welcome via GitHub issues and pull requests.

## License

MIT

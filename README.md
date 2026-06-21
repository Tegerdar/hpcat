# hpcat

HPC Administration & Telemetry Tool

A lightweight Python CLI for querying hardware metrics in Slurm-managed HPC clusters.

## Features

- **GPU Telemetry**: Real-time GPU metrics (utilization, memory, temperature, power) gathered via SSH and nvidia-smi on GPU nodes
- **CPU State**: OS-level CPU information (via lscpu) plus Slurm per-node CPU allocation and load
- **Memory Telemetry**: OS memory details (from /proc/meminfo) and Slurm memory allocation/state
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

### Output Format Examples
Append a format flag to any command:
```bash
hpcat gpu -j        # JSON
hpcat gpu -c        # CSV
hpcat gpu -p        # Prometheus (OpenMetrics)
hpcat cpu -e -j     # Extended CPU info in JSON
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
- Network reachability / SSH key setup so the execution host can SSH into compute nodes (BatchMode=no/keys)

If Slurm discovery fails or required utilities are missing, hpcat will print an error and fall back to user-supplied node lists when possible.

## Exit codes

- `0` — success
- non-zero — failure or no targets identified (examples: 1 for no targets, 130 for keyboard interrupt)

## Contributing

Bug reports, feature requests, and patches are welcome via GitHub issues and pull requests.

## License

MIT

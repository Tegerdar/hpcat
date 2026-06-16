# hpcat

Modern HPC Cluster Administration & Telemetry

A lightweight Python CLI for querying GPU hardware metrics and compute node allocation state in Slurm-managed HPC clusters.

## Features

- **GPU Telemetry**: Real-time GPU metrics (utilization, memory, temperature, power) via SSH
- **Node Status**: CPU and memory allocation state from Slurm
- **Flexible Output**: Human-readable tables, JSON, CSV, or Prometheus OpenMetrics formats
- **Parallel Discovery**: Efficient batch polling with configurable concurrency

## Installation

```bash
pip install hpcat
```

## Usage

### GPU Metrics
Query GPU status across all GPU nodes:
```bash
hpcat gpu
```

Poll specific nodes:
```bash
hpcat gpu -n node01 node02 node03
```

### Node Allocation
View CPU and memory allocation:
```bash
hpcat nodes
```

### Output Formats
Append format flags to any command:
```bash
hpcat gpu -j        # JSON
hpcat gpu -c        # CSV
hpcat gpu -p        # Prometheus
hpcat nodes -j      # works with nodes too
```

## Requirements

- Python >= 3.9
- `ssh` (for GPU metrics polling)
- `sinfo` (Slurm utilities)

## License

MIT

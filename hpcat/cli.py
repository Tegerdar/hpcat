import argparse
import sys

from hpcat.commands import gpu, cpu, mem


def main() -> None:
    parser = argparse.ArgumentParser(
        description="hpcat: Modern HPC Cluster Administration & Telemetry",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
GLOBAL FORMATTING OPTIONS:
  These flags can be appended to any subcommand to change the output format:
    -j, --json        Output in machine-readable JSON
    -c, --csv         Output in flattened CSV format
    -p, --prometheus  Output in Prometheus OpenMetrics format

  Example: 
    hpcat gpu -j
    hpcat cpu -p
        """
    )
    
    subparsers = parser.add_subparsers(
        dest="command", 
        required=True, 
        help="Target subsystem to query"
    )

    # --- Subcommand definitions ---
    parser_gpu = subparsers.add_parser(
        "gpu", 
        help="Real-time GPU hardware telemetry via SSH"
    )
    parser_gpu.add_argument(
        "-n", "--nodes",
        nargs="+",
        metavar="NODE",
        help="List of nodes to target (overrides Slurm discovery)"
    )

    parser_cpu = subparsers.add_parser(
        "cpu",
        help="CPU state"
    )
    parser_cpu.add_argument(
        "-n", "--nodes",
        nargs="+",
        metavar="NODE",
        help="List of nodes to target (overrides Slurm discovery)"
    )
    parser_cpu.add_argument(
        "-e", "--extended",
        action="store_true",
        help="Include exhaustive CPU parameters (flags, vulnerabilities, NUMA mapping)"
    )

    parser_mem = subparsers.add_parser(
        "mem",
        help="Include exhaustive CPU parameters (flags, vulnerabilities, NUMA mapping)"
    )
    parser_mem.add_argument(
        "-n", "--nodes",
        nargs="+",
        metavar="NODE",
        help="List of nodes to target (overrides Slurm discovery)"
    )

    # --- Standardized Output Formatting ---
    for subp in [parser_gpu, parser_mem, parser_cpu]:
        format_group = subp.add_mutually_exclusive_group()
        format_group.add_argument("-j", "--json", action="store_true", help="Output in machine-readable JSON")
        format_group.add_argument("-c", "--csv", action="store_true", help="Output in flattened CSV format")
        format_group.add_argument("-p", "--prometheus", action="store_true", help="Output in Prometheus OpenMetrics format")

    args = parser.parse_args()

    try:
        if args.command == "gpu":
            sys.exit(gpu.execute(args))
        elif args.command == "cpu":
            sys.exit(cpu.execute(args))
        elif args.command == "mem":
            sys.exit(mem.execute(args))
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\nFatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

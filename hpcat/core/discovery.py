import subprocess
import sys
from typing import List, Optional


def discover_nodes(gres_filter: Optional[str] = None) -> List[str]:
    """Discover compute nodes via `sinfo`.

    gres_filter: if given (e.g. "gpu"), only nodes whose GRES string contains
    it (case-insensitive) are returned - this is what gpu.py used to do with
    its own copy of this function. Leave it None for "all nodes", which is
    what cpu/mem/network/storage want.
    """
    fmt = "%n|%G" if gres_filter else "%n"
    try:
        result = subprocess.run(
            ["sinfo", "-N", "-h", "-o", fmt],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Slurm discovery failed: {e}", file=sys.stderr)
        return []

    nodes = set()
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        if gres_filter:
            node, gres = line.split("|", 1)
            if gres_filter.lower() in gres.lower():
                nodes.add(node.strip())
        else:
            nodes.add(line.strip())
    return sorted(nodes)


def resolve_nodes(args, gres_filter: Optional[str] = None) -> List[str]:
    """`-n/--nodes` on the CLI always wins over discovery; this is the
    override-vs-discover decision every command's execute() repeated."""
    explicit = getattr(args, "nodes", None)
    return explicit if explicit else discover_nodes(gres_filter)

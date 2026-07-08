# hpcat/commands/storage.py
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple

# Import the decoupled formatters
from hpcat.formatters import json_out, csv_out, prometheus_out

SSH_TIMEOUT = 5  # storage queries (beegfs-df, lfs df) can be slower than sysfs reads
MAX_WORKERS = 30

# Pseudo-filesystems to exclude from the generic df listing - none of these
# represent real storage capacity worth reporting on.
DF_SKIP_FSTYPES = {
    "tmpfs", "devtmpfs", "proc", "sysfs", "cgroup", "cgroup2", "overlay",
    "squashfs", "devpts", "autofs", "mqueue", "debugfs", "tracefs",
    "securityfs", "pstore", "hugetlbfs", "nsfs", "rpc_pipefs", "fusectl",
}

# Remote-side collector. Root-free by design (matches the pattern used by
# mem.py / cpu.py / network.py). Three record types, one line each:
#   MOUNT|<source>|<fstype>|<1k_blocks>|<used>|<avail>|<pcent>|<mountpoint>
#   BEEGFS_SECTION|<meta|storage>
#   BEEGFS_ROW|<raw beegfs-df row text>
#   LUSTRE_ROW|<raw lfs df -h row text>
#
# beegfs-df and lfs df output is intentionally passed through as raw text
# rather than pre-parsed remotely: their column layout varies across BeeGFS
# versions (some include a "Cap." column, some don't) and lfs df formatting
# varies by Lustre version too. Parsing happens locally in Python where it's
# easier to be defensive about layout differences and version drift.
REMOTE_SCRIPT = r"""
df -PT 2>/dev/null | tail -n +2 | while IFS= read -r line; do
  echo "MOUNT|${line}"
done

if command -v beegfs-df >/dev/null 2>&1; then
  section="unknown"
  beegfs-df 2>/dev/null | while IFS= read -r line; do
    case "$line" in
      *METADATA*SERVERS*) echo "BEEGFS_SECTION|meta"; continue ;;
      *STORAGE*TARGETS*) echo "BEEGFS_SECTION|storage"; continue ;;
      TargetID*|========*|"") continue ;;
    esac
    echo "BEEGFS_ROW|${line}"
  done
fi

if command -v lfs >/dev/null 2>&1; then
  lfs df -h 2>/dev/null | tail -n +2 | while IFS= read -r line; do
    echo "LUSTRE_ROW|${line}"
  done
fi
"""

# Defensive beegfs-df row matcher. Handles both the classic layout
# (TargetID Pool Total Free % ITotal IFree %) and the newer one that adds a
# "Cap." column before Pool - the optional non-greedy token absorbs it when
# present without requiring an exact column count.
_BEEGFS_ROW_RE = re.compile(
    r'^\s*(?P<target_id>\d+)\s+'
    r'(?:\S+\s+)?'                            # optional Cap. column
    r'(?P<pool>\[?\w+\]?)\s+'
    r'(?P<total>[\d.]+\s*[KMGTP]i?B)\s+'
    r'(?P<free>[\d.]+\s*[KMGTP]i?B)\s+'
    r'(?P<free_pct>\d+)%\s+'
    r'(?P<itotal>[\d.]+M)\s+'
    r'(?P<ifree>[\d.]+M)\s+'
    r'(?P<ifree_pct>\d+)%\s*$'
)

# lfs df -h row format (both MDT and OST lines share this shape):
#   fsname-MDTxxxx_UUID   <total>  <used>  <avail>  <use%>  <mount>[state]
_LUSTRE_ROW_RE = re.compile(
    r'^\s*(?P<target>\S+)\s+'
    r'(?P<total>[\d.]+[KMGTP]?)\s+'
    r'(?P<used>[\d.]+[KMGTP]?)\s+'
    r'(?P<avail>[\d.]+[KMGTP]?)\s+'
    r'(?P<use_pct>\d+)%\s+'
    r'(?P<mount>\S+)'
    r'(?:\[(?P<state>[^\]]*)\])?\s*$'
)


def get_storage_nodes() -> List[str]:
    """Discover all compute nodes via Slurm."""
    try:
        result = subprocess.run(
            ['sinfo', '-N', '-h', '-o', '%n'],
            capture_output=True, text=True, check=True
        )
        nodes = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        return list(set(nodes))
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Slurm discovery failed: {e}", file=sys.stderr)
        return []


def _parse_beegfs_row(raw: str) -> Dict[str, Any]:
    if raw.strip().startswith("[ERROR"):
        return {"error": raw.strip()}
    m = _BEEGFS_ROW_RE.match(raw)
    if m:
        d = m.groupdict()
        d["free_pct"] = int(d["free_pct"])
        d["ifree_pct"] = int(d["ifree_pct"])
        return d
    return {"unparsed": raw.strip()}


def _parse_lustre_row(raw: str) -> Dict[str, Any]:
    m = _LUSTRE_ROW_RE.match(raw)
    if m:
        d = m.groupdict()
        try:
            d["use_pct"] = int(d["use_pct"])
        except (TypeError, ValueError):
            pass
        return d
    return {"unparsed": raw.strip()}


def _parse_remote_output(stdout: str) -> Dict[str, Any]:
    """Turn the delimited remote script output into a structured dict:
    {
        "mounts": [ {source, fstype, blocks_1k, used_1k, avail_1k, pcent, mountpoint}, ... ],
        "beegfs": {"meta": [row, ...], "storage": [row, ...]},
        "lustre": [row, ...],
    }
    """
    mounts = []
    beegfs: Dict[str, List[Dict[str, Any]]] = {"meta": [], "storage": []}
    lustre = []
    beegfs_section = None

    for line in stdout.strip().split('\n'):
        if not line or '|' not in line:
            continue
        record, _, rest = line.partition('|')

        if record == "MOUNT":
            fields = rest.split(None, 6)
            if len(fields) != 7:
                continue
            source, fstype, blocks, used, avail, pcent, mountpoint = fields
            if fstype in DF_SKIP_FSTYPES:
                continue
            mounts.append({
                "source": source,
                "fstype": fstype,
                "blocks_1k": blocks,
                "used_1k": used,
                "avail_1k": avail,
                "pcent": pcent,
                "mountpoint": mountpoint,
            })

        elif record == "BEEGFS_SECTION":
            beegfs_section = rest.strip()

        elif record == "BEEGFS_ROW":
            target = "meta" if beegfs_section == "meta" else "storage"
            beegfs[target].append(_parse_beegfs_row(rest))

        elif record == "LUSTRE_ROW":
            lustre.append(_parse_lustre_row(rest))

    return {"mounts": mounts, "beegfs": beegfs, "lustre": lustre}


def poll_node(node: str) -> Tuple[str, Dict[str, Any]]:
    """Fetch generic mount usage plus BeeGFS/Lustre target detail via SSH.

    Root-free: `df`, `beegfs-df`, and `lfs df` are all readable without
    elevated privileges. If beegfs-df / lfs are not installed on a node, those
    sections are simply empty rather than an error - this is expected on
    nodes that aren't BeeGFS/Lustre clients.
    """
    cmd = [
        'ssh',
        '-o', 'BatchMode=yes',
        '-o', f'ConnectTimeout={SSH_TIMEOUT}',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'LogLevel=QUIET',
        node,
        REMOTE_SCRIPT,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=SSH_TIMEOUT + 3)
        if result.returncode != 0:
            return node, {"error": "ssh_auth_or_storage_query_failed"}
        return node, _parse_remote_output(result.stdout)
    except subprocess.TimeoutExpired:
        return node, {"error": "timeout"}
    except Exception as e:
        return node, {"error": str(e)}


def execute(args: Any) -> int:
    """Main execution router for the storage subcommand."""
    target_nodes = args.nodes if getattr(args, 'nodes', None) else get_storage_nodes()
    if not target_nodes:
        print("No targets identified. Exiting.", file=sys.stderr)
        return 1

    extended = getattr(args, 'extended', False)
    cluster_state = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(poll_node, node): node for node in target_nodes}
        for future in as_completed(futures):
            node, node_data = future.result()
            cluster_state[node] = node_data

    # Route raw dictionary to the requested formatter
    if getattr(args, 'prometheus', False):
        print(prometheus_out.render(cluster_state, module="storage"))
    elif getattr(args, 'csv', False):
        print(csv_out.render(cluster_state, module="storage"))
    elif getattr(args, 'json', False):
        print(json_out.render(cluster_state, module="storage"))
    else:
        print_console(cluster_state, extended)

    return 0


def _blocks_to_gb(blocks_1k: str) -> float:
    try:
        return int(blocks_1k) / (1024 * 1024)
    except ValueError:
        return 0.0


def _pcent_int(pcent: str) -> int:
    try:
        return int(pcent.rstrip('%'))
    except (ValueError, AttributeError):
        return -1


def print_console(data: Dict[str, Dict[str, Any]], extended: bool = False) -> None:
    """Formats the storage data into a clean terminal table."""
    print("=" * 110)
    print(f"{'Node':<12} | {'Mount':<28} | {'FSType':<12} | {'Size':<9} | {'Used':<9} | {'Avail':<9} | {'Use%'}")
    print("=" * 110)

    for node in sorted(data.keys()):
        node_data = data[node]

        if "error" in node_data:
            print(f"{node:<12} | [ ERROR: {node_data['error']} ]")
            continue

        for m in node_data.get("mounts", []):
            size_gb = _blocks_to_gb(m["blocks_1k"])
            used_gb = _blocks_to_gb(m["used_1k"])
            avail_gb = _blocks_to_gb(m["avail_1k"])
            use_pct = _pcent_int(m["pcent"])

            marker = "  <-- LOW SPACE" if use_pct >= 90 else ""
            print(
                f"{node:<12} | {m['mountpoint']:<28} | {m['fstype']:<12} | "
                f"{size_gb:>7.1f}G | {used_gb:>7.1f}G | {avail_gb:>7.1f}G | {m['pcent']:>4}{marker}"
            )

    print("=" * 110)

    # BeeGFS / Lustre target-level detail - shown whenever present, since this
    # is the whole point of the module (capacity pool / target-level free%,
    # not just the client-side mount aggregate that df alone would show).
    has_beegfs = any(
        node_data.get("beegfs", {}).get("meta") or node_data.get("beegfs", {}).get("storage")
        for node_data in data.values() if "error" not in node_data
    )
    has_lustre = any(
        node_data.get("lustre") for node_data in data.values() if "error" not in node_data
    )

    if has_beegfs:
        print("\n[ BeeGFS Targets ]")
        for node in sorted(data.keys()):
            node_data = data[node]
            if "error" in node_data:
                continue
            beegfs = node_data.get("beegfs", {})
            if not beegfs.get("meta") and not beegfs.get("storage"):
                continue
            print(f"\n--- {node} ---")
            for kind, rows in (("Metadata", beegfs.get("meta", [])), ("Storage", beegfs.get("storage", []))):
                if not rows:
                    continue
                print(f"  {kind}:")
                for r in rows:
                    if "error" in r:
                        print(f"    [ERROR] {r['error']}")
                    elif "unparsed" in r:
                        print(f"    [unparsed] {r['unparsed']}")
                    else:
                        marker = "  <-- LOW FREE%" if r["free_pct"] <= 10 else ""
                        print(
                            f"    target={r['target_id']:<6} pool={r['pool']:<10} "
                            f"total={r['total']:<10} free={r['free']:<10} free%={r['free_pct']:>3}%{marker}"
                        )

    if has_lustre:
        print("\n[ Lustre Targets ]")
        for node in sorted(data.keys()):
            node_data = data[node]
            if "error" in node_data:
                continue
            rows = node_data.get("lustre", [])
            if not rows:
                continue
            print(f"\n--- {node} ---")
            for r in rows:
                if "unparsed" in r:
                    print(f"    [unparsed] {r['unparsed']}")
                else:
                    use_pct = r.get("use_pct", -1)
                    marker = "  <-- LOW SPACE" if isinstance(use_pct, int) and use_pct >= 90 else ""
                    print(
                        f"    target={r['target']:<28} total={r['total']:<8} "
                        f"used={r['used']:<8} avail={r['avail']:<8} use%={r['use_pct']:>3}%{marker}"
                    )

    if extended:
        print("\n[ Extended: Raw Mount Details ]")
        for node in sorted(data.keys()):
            node_data = data[node]
            if "error" in node_data:
                continue
            print(f"\n--- {node} ---")
            for m in node_data.get("mounts", []):
                print(f"  {m['mountpoint']}:")
                for k, v in m.items():
                    print(f"    {k:<12}: {v}")

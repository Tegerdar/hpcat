from typing import Any, Callable, Dict

from hpcat.formatters import csv_out, json_out, prometheus_out


def render_or_print(
    args: Any,
    cluster_state: Dict[str, Dict[str, Any]],
    module: str,
    console_fn: Callable[..., None],
    *console_args: Any,
) -> None:
    if getattr(args, "prometheus", False):
        print(prometheus_out.render(cluster_state, module=module))
    elif getattr(args, "csv", False):
        print(csv_out.render(cluster_state, module=module))
    elif getattr(args, "json", False):
        print(json_out.render(cluster_state, module=module))
    else:
        console_fn(cluster_state, *console_args)

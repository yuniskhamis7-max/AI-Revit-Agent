"""Context snapshot serialization utilities."""

import json
import os


def to_json(snapshot):
    """Serialize a context snapshot for logs, display, or persistence."""
    return json.dumps(snapshot, indent=4, sort_keys=True)


def save_snapshot(snapshot, path):
    """Save a context snapshot to a JSON file."""
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)

    with open(path, "w") as snapshot_file:
        snapshot_file.write(to_json(snapshot))

    return path

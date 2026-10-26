"""Durable task records for a future agent; success is a verified outcome."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def pose_record(stamped):
    p, q = stamped.pose.position, stamped.pose.orientation
    # Preserve invalid request evidence as JSON null rather than emitting NaN.
    def finite(values):
        return [v if math.isfinite(v) else None for v in values]
    return {'frame': stamped.header.frame_id, 'position': finite([p.x, p.y, p.z]),
            'orientation': finite([q.x, q.y, q.z, q.w])}


def write_report(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)

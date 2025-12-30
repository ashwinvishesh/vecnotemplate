import time
import re
import os
import threading
from flask import Flask, jsonify
# =========================
# V3 Script
# =========================
# Configuration
# =========================

LOG_FILE = "/root/debug.log"
STALE_THRESHOLD_SEC = 30
READ_BACK_LINES = 300
LOG_POLL_INTERVAL = 0.2

# =========================
# App & State
# =========================

app = Flask(__name__)

state_lock = threading.Lock()

state = {
    "total_hashrate_mh": None,
    "gpu_hashrates": {},     # gpu_id -> {name, hashrate_mh}
    "last_update": None
}

# =========================
# Regex (robust)
# =========================

TOTAL_REGEX = re.compile(
    r"Total\s+hashrate:\s*([\d.]+)\s*Mhash/s",
    re.IGNORECASE
)

GPU_REGEX = re.compile(
    r"GPU\s*#(\d+)\s+(.+?)\s+hashrate:\s*([\d.]+)\s*Mhash/s",
    re.IGNORECASE
)

# =========================
# Log Processing
# =========================

def process_line(line: str):
    now = time.time()

    total_match = TOTAL_REGEX.search(line)
    if total_match:
        with state_lock:
            state["total_hashrate_mh"] = float(total_match.group(1))
            state["gpu_hashrates"].clear()  # reset GPUs on new cycle
            state["last_update"] = now
        return

    gpu_match = GPU_REGEX.search(line)
    if gpu_match:
        gpu_id = int(gpu_match.group(1))
        gpu_name = gpu_match.group(2).strip()
        hashrate = float(gpu_match.group(3))

        with state_lock:
            state["gpu_hashrates"][gpu_id] = {
                "name": gpu_name,
                "hashrate_mh": hashrate
            }
            state["last_update"] = now

# =========================
# Log Follower
# =========================

def follow_log():
    last_inode = None
    file_offset = 0

    while True:
        if not os.path.exists(LOG_FILE):
            time.sleep(1)
            continue

        try:
            stat = os.stat(LOG_FILE)
            inode = stat.st_ino

            # Detect new file / rotation
            if inode != last_inode:
                last_inode = inode
                file_offset = 0

                with open(LOG_FILE, "r") as f:
                    lines = f.readlines()[-READ_BACK_LINES:]
                    for line in lines:
                        process_line(line)
                    file_offset = f.tell()

            with open(LOG_FILE, "r") as f:
                f.seek(file_offset)

                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(LOG_POLL_INTERVAL)
                        if not os.path.exists(LOG_FILE):
                            break
                        continue

                    process_line(line)
                    file_offset = f.tell()

        except Exception as e:
            print(f"[log-follow] error: {e}")
            time.sleep(1)

# =========================
# API
# =========================

@app.route("/stats")
def stats():
    now = time.time()

    with state_lock:
        gpus_array = [
            {
                "id": gpu_id,
                "gpu_name": gpu["name"],
                "hashrate_mh": gpu["hashrate_mh"]
            }
            for gpu_id, gpu in sorted(state["gpu_hashrates"].items())
        ]

        last_update = state["last_update"]
        total_hashrate = state["total_hashrate_mh"]

    stale = (
        last_update is None or
        now - last_update > STALE_THRESHOLD_SEC
    )

    return jsonify({
        "total_hashrate_mh": total_hashrate,
        "gpu_count": len(gpus_array),
        "gpus": gpus_array,
        "last_update": last_update,
        "stale": stale
    })

# =========================
# Main
# =========================

if __name__ == "__main__":
    threading.Thread(target=follow_log, daemon=True).start()

    # Bind to localhost only
    app.run(host="127.0.0.1", port=8080)

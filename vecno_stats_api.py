import time
import re
import os
from flask import Flask, jsonify

# =========================
# Configuration
# =========================

LOG_FILE = "/root/debug.log"
STALE_THRESHOLD_SEC = 30
READ_BACK_LINES = 300

# =========================
# App & State
# =========================

app = Flask(__name__)

state = {
    "total_hashrate_mh": None,
    "gpu_count": 0,
    "gpu_hashrates": {},   # internal map: gpu_id -> {name, hashrate_mh}
    "last_update": None
}

# =========================
# Regex (hardened)
# =========================

TOTAL_REGEX = re.compile(
    r"Total hashrate:\s*([\d.]+)\s*Mhash/s.*\(\s*(\d+)\s+CPU.*?,\s*(\d+)\s+GPU",
    re.IGNORECASE
)

GPU_REGEX = re.compile(
    r"GPU\s+#(\d+)\s+(.+?)\s+hashrate:\s*([\d.]+)\s*Mhash/s",
    re.IGNORECASE
)

# =========================
# Log Processing
# =========================

def process_line(line: str):
    total_match = TOTAL_REGEX.search(line)
    if total_match:
        state["total_hashrate_mh"] = float(total_match.group(1))
        state["gpu_count"] = int(total_match.group(3))
        state["last_update"] = time.time()
        return

    gpu_match = GPU_REGEX.search(line)
    if gpu_match:
        gpu_id = int(gpu_match.group(1))
        gpu_name = gpu_match.group(2).strip()
        hashrate = float(gpu_match.group(3))

        state["gpu_hashrates"][gpu_id] = {
            "name": gpu_name,
            "hashrate_mh": hashrate
        }

def follow_log():
    while True:
        if not os.path.exists(LOG_FILE):
            time.sleep(1)
            continue

        try:
            with open(LOG_FILE, "r") as f:
                # 1️⃣ Process recent history
                lines = f.readlines()[-READ_BACK_LINES:]
                for line in lines:
                    process_line(line)

                # 2️⃣ Follow new lines
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.2)
                        if not os.path.exists(LOG_FILE):
                            break  # log rotated or miner restarted
                        continue

                    process_line(line)

        except Exception as e:
            print(f"[log-follow] error: {e}")
            time.sleep(1)

# =========================
# API
# =========================

@app.route("/stats")
def stats():
    now = time.time()

    gpus_array = [
        {
            "id": gpu_id,
            "gpu_name": gpu["name"],
            "hashrate_mh": gpu["hashrate_mh"]
        }
        for gpu_id, gpu in sorted(state["gpu_hashrates"].items())
    ]

    stale = (
        state["last_update"] is None or
        now - state["last_update"] > STALE_THRESHOLD_SEC
    )

    return jsonify({
        "total_hashrate_mh": state["total_hashrate_mh"],
        "gpu_count": state["gpu_count"],
        "gpus": gpus_array,
        "last_update": state["last_update"],
        "stale": stale
    })

# =========================
# Main
# =========================

if __name__ == "__main__":
    import threading

    threading.Thread(target=follow_log, daemon=True).start()

    # Bind to localhost only (secure, Clore-safe)
    app.run(host="127.0.0.1", port=8080)

import time
import re
from flask import Flask, jsonify

LOG_FILE = "/root/debug.log"

app = Flask(__name__)

state = {
    "total_hashrate_mh": None,
    "gpu_hashrates": {},
    "gpu_count": 0,
    "last_update": None
}

TOTAL_REGEX = re.compile(
    r"Total hashrate:\s*([\d.]+)\s*Mhash/s.*\((\d+)\s+CPU.*,\s*(\d+)\s+GPUs\)"
)

GPU_REGEX = re.compile(
    r"GPU\s+#(\d+)\s+(.+?)\s+hashrate:\s*([\d.]+)\s*Mhash/s"
)

def follow_log():
    with open(LOG_FILE, "r") as f:
        f.seek(0, 2)  # jump to end
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.2)
                continue

            total_match = TOTAL_REGEX.search(line)
            if total_match:
                state["total_hashrate_mh"] = float(total_match.group(1))
                state["gpu_count"] = int(total_match.group(3))
                state["last_update"] = time.time()
                continue

            gpu_match = GPU_REGEX.search(line)
            if gpu_match:
                gpu_id = int(gpu_match.group(1))
                gpu_name = gpu_match.group(2).strip()
                hashrate = float(gpu_match.group(3))

                state["gpu_hashrates"][gpu_id] = {
                    "name": gpu_name,
                    "hashrate_mh": hashrate
                }

@app.route("/stats")
def stats():
    return jsonify({
        "total_hashrate_mh": state["total_hashrate_mh"],
        "gpu_count": state["gpu_count"],
        "gpus": state["gpu_hashrates"],
        "last_update": state["last_update"],
        "stale": (
            state["last_update"] is None or
            time.time() - state["last_update"] > 30
        )
    })

if __name__ == "__main__":
    import threading
    threading.Thread(target=follow_log, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)


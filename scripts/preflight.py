"""Execute local acceptance gates without touching runtime user datasets."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    required = [
        "README.md", "requirements.lock", "Dockerfile", ".dockerignore",
        "docs/ARCHITECTURE.md", "docs/COMPLIANCE.md",
        "docs/METHODOLOGY.md", "docs/DATA_MAPPING.md",
        "frontend/index.html", "frontend/app.js", "frontend/styles.css",
        "frontend/i18n.js", "localization.py",
        "engine.py", "importer.py", "partner_xlsx.py", "demo_data.py",
        "server.py", "storage.py", "exports.py",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    if missing:
        print("Missing required files: " + ", ".join(missing))
        return 1
    checks = [("Python tests", [sys.executable, "-m", "pytest", "tests", "-q"])]
    if shutil.which("node"):
        checks.append(("Browser JavaScript syntax", ["node", "--check", "frontend/app.js"]))
        checks.append(("Language catalogue syntax", ["node", "--check", "frontend/i18n.js"]))
    else:
        print("Node is unavailable: JavaScript syntax check not run.")
    for label, command in checks:
        print(f"Checking: {label}", flush=True)
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            return result.returncode
    print("Local preflight passed. This does not verify the platform submission or Docker build.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

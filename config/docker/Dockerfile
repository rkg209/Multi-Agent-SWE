FROM python:3.11-slim

WORKDIR /workspace

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (copy requirements separately for layer caching)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install sb-cli (SWE-bench CLI)
RUN pip install --no-cache-dir swebench

# Non-root user for the run-code sandbox (NFR-2); created last since the
# installs above need root.
RUN useradd -m -u 1000 sandbox
USER sandbox

# Default: do nothing (sandbox_exec.py passes the script as CMD)
ENTRYPOINT ["python"]

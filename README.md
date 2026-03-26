# Wire Fact Gathering Tool

A diagnostic and health-checking tool for Wire backend installations. Operators run a gatherer script on their deployment infrastructure, which collects data about every component of the Wire stack. The results are then uploaded to a web UI that analyzes them and produces an interactive health report with recommendations.

The name "linter" comes from how the tool examines collected facts and checks them against known-good thresholds similar to how a code linter checks source code for problems.

## Quickstart

### What you need

- **Any machine with a browser** to run the UI (your laptop, a jump host, anything)
- **The Wire admin host** (the machine running the `wire-server-deploy` container) with SSH access to the Wire infrastructure
- **Python 3.10+** wherever the gatherer script will run (ships by default on Ubuntu 22.04+, no pip install needed)

The gatherer can run in three modes:

| Mode | Where the script runs | `--source` flag | How it reaches infrastructure |
|------|----------------------|-----------------|-------------------------------|
| **Admin host** (default) | Directly on the Wire admin host | `--source admin-host` | Direct connections to VMs and databases, kubectl for Kubernetes |
| **SSH into admin host** | Your local machine | `--source ssh-into-admin-host` | Tunnels through the admin host as an SSH jump host to reach VMs and databases |
| **Client** | Any machine on the target network | `--source client` | No SSH or kubectl, only tests external reachability (DNS, TLS, HTTP, WebSocket) |

Additionally, `--only-through-kubernetes` can be combined with admin-host or ssh-into-admin-host mode to skip all SSH-dependent targets and only use kubectl.

**Admin host mode** is the default and the most common. You run the script directly on the Wire deploy host where it can reach all VMs, databases, and Kubernetes without any SSH jumping. **SSH into admin host mode** is for when you want to run the script from your laptop or a jump host and have it SSH through the admin host to reach everything. **Client mode** is for testing reachability from a client network perspective: it checks DNS resolution, TLS certificates, HTTP endpoints, WebSocket connectivity, calling servers, and federation, but doesn't access any backend infrastructure. **Kubernetes-only mode** is for deployments where you only have kubectl access and no SSH to any VMs or database hosts (common with managed Kubernetes or certain on-prem setups). It skips all SSH-dependent targets and produces a partial report covering Kubernetes health, Wire service status, ConfigMap validation, and configuration analysis.

### 1. Get the tool

From a zip file:
```bash
unzip wire-linter.zip
cd wire-linter
```

From GitHub:
```bash
git clone <repo-url>
cd wire-linter
```

No build step is needed the UI is pre-built as a single self-contained HTML file.

### 2. Open the UI

Open `ui/dist/index.html` in any browser directly from the filesystem:

```bash
# Linux
xdg-open ui/dist/index.html

# macOS
open ui/dist/index.html

# Or just double-click the file in your file manager
```

No web server required the entire application (HTML, CSS, JS, fonts) is bundled into a single file.

At this point, you can just follow the instructions of the "wizard" step by step in the web UI. 

The UI guides you through configuring the tool, running the gatherer, and uploading results to see the report.

Alternatively, if you plan to edit the code for the web UI, you can run the Vite dev server:

```bash
cd ui/
bun run dev
```

The dev server will then become available on `http://localhost:5173` and supports hot module reloading for frontend development.

### 3. Configure your Wire installation (Steps 1-3 in the UI)

1. **(Optional) Upload your Ansible inventory** (`hosts.ini` or `inventory.yml`) to pre-fill connection details
2. **Review the configuration form** admin host IP, SSH user and key, database hosts, Kubernetes namespace, feature flags. Edit as needed.
3. **Copy the generated settings file** the UI produces a `wire-facts-settings.yaml`. Click the copy button.

### 4. Run the gatherer (Step 4)

Save the settings YAML you copied from the UI to a file:

```bash
cat > /tmp/wire-facts-settings.yaml << 'EOF'
# Paste the YAML you copied from the UI here
EOF
```
```bash
nano /tmp/wire-facts-settings.yaml
```

```bash
vi /tmp/wire-facts-settings.yaml
```

Then choose one of the three modes:

#### Option A: Run on the admin host (default)

This is the default and the most common option. Copy the project and settings file to the Wire admin host, then run:

```bash
python3 src/script/runner.py \
    --config /tmp/wire-facts-settings.yaml \
    --output /tmp/wire-facts-results.jsonl
```

The `--source admin-host` flag is the default and can be omitted. The script connects directly to VMs and databases since it's already on the same network.

#### Option B: Run from your local machine (SSH into admin host)

The script runs on your machine and uses the admin host as an SSH jump host to reach all VMs, databases, and Kubernetes:

```bash
python3 src/script/runner.py \
    --config /tmp/wire-facts-settings.yaml \
    --output /tmp/wire-facts-results.jsonl \
    --source ssh-into-admin-host
```

You need SSH access (user + key) to the admin host, which is configured in the settings YAML. All SSH connections (to database VMs, kubenodes, etc.) are routed through the admin host automatically.

#### Option C: Client mode (external reachability only)

For testing how Wire looks from a client network, with no SSH or kubectl needed:

```bash
python3 src/script/runner.py \
    --config /tmp/wire-facts-settings.yaml \
    --output /tmp/wire-facts-results.jsonl \
    --source client \
    --network-name office-lan
```

This runs a different set of targets that test DNS resolution, TLS certificates, HTTP endpoints, WebSocket connectivity, calling server reachability, and federation from the perspective of a client machine. The `--network-name` flag is a label that gets stored in the output so you can tell apart runs from different networks.

#### Option D: Kubernetes-only mode (no SSH access)

For deployments where you only have kubectl access and no SSH to any VMs or database hosts:

```bash
python3 src/script/runner.py \
    --config /tmp/wire-facts-settings.yaml \
    --output /tmp/wire-facts-results.jsonl \
    --only-through-kubernetes
```

This skips all targets that require SSH (database health, VM metrics, host checks, etc.) and only runs targets that use kubectl. The resulting report covers about 60% of the normal checks: Kubernetes cluster health, Wire service status, ConfigMap schema validation, configuration analysis, Redis (via kubectl exec), secrets, and migrations.

In the web UI, checkers that depend on SSH-collected data are automatically greyed out as "N/A" so you can see exactly what was and wasn't checked.

This flag can be combined with `--source admin-host` (default) or `--source ssh-into-admin-host`.

### 5. Upload results and view the report (Steps 5-6)

1. Copy `/tmp/wire-facts-results.jsonl` to the machine where you have the browser open (skip this if you ran in ssh-into-admin-host or client mode, the file is already local)
2. In the UI, click **Next** to reach the Upload step
3. Upload (or paste) the JSONL file
4. The report appears immediately with:
   - Summary cards showing healthy / warning / unhealthy counts
   - Interactive tree table with all check results grouped by category
   - Expandable details with raw command output for each check
   - Actionable recommendations for any warnings or failures
   - PDF export button for sharing

## Architecture Overview

The tool has two main parts:

**1. Web UI** A Vue 3 single-page application built as a single self-contained HTML file (all CSS, JS, and fonts bundled together). It walks the operator through a 6-step wizard to configure, run, and review the health check. Analysis is done entirely in the browser using 172 TypeScript checker classes.

**2. Gatherer Script** A Python script that runs on the operator's Wire admin host (or remotely via SSH, or in client mode from any machine). It discovers and executes 193 target collectors that probe every part of the Wire infrastructure (Kubernetes, databases, VMs, HTTP APIs, host machine, and external client reachability) and outputs a JSONL file containing one data point per line. Uses only Python standard library, no pip install required.

These two parts are connected by a manual handoff: the UI generates a settings file, the operator runs the gatherer with it, then uploads the resulting JSONL back into the UI.

## The Full Process

### Step 1 Host File (optional)

The operator can paste or upload their Ansible inventory file (`hosts.ini` / `inventory.yml`) from their Wire deployment. The UI parses it and pre-fills the configuration form with IPs, hostnames, SSH user, and other details it can extract.

This step can be skipped entirely the operator can fill in the configuration manually in the next step.

### Step 2 Configuration

A form where the operator reviews and edits connection details for their Wire installation:

- **Admin host IP** the deploy machine
- **SSH user and key path** credentials for reaching VMs
- **Database hosts** Cassandra, Elasticsearch, MinIO, PostgreSQL IPs
- **Kubernetes namespace** and **cluster domain**
- **SSH port**
- **Deployment feature flags** (MLS, federation, etc.)

If Step 1 was used, these fields are already pre-filled.

### Step 3 Settings File

Based on the configuration, the UI generates a `wire-facts-settings.yaml` file. The operator copies this YAML to their deploy host (the machine where `wire-server-deploy` lives). The file contains all the connection details the gatherer script needs, with comments explaining each field.

The UI displays the YAML with a copy button for easy clipboard access.

### Step 4 Run the Gatherer

The operator switches from the browser to a terminal on their deploy host and runs the gatherer script. The UI shows two options:

```
python3 src/script/runner.py --config /tmp/wire-facts-settings.yaml --output /tmp/wire-facts-results.jsonl
```

CLI flags:

| Flag | Description |
|------|-------------|
| `--config` | Path to the YAML config file (required) |
| `--output` | Path to output JSONL file (required unless `--only-preflight-checks` or `--dry-run`) |
| `--target` | Target filter, e.g. `databases/cassandra/*` (default: `*`) |
| `--parallel N` | Run N targets concurrently (default: 1, sequential) |
| `--source` | Where the gatherer runs: `admin-host` (default), `ssh-into-admin-host`, or `client` |
| `--network-name` | Human-readable label for this run (e.g. `office-lan`, `home-vpn`), stored in the output |
| `--kubeconfig` | Explicit path to kubeconfig file (sets KUBECONFIG env var for kubectl) |
| `--cluster-type` | Which cluster to target: `both` (default), `main`, or `calling` |
| `--verbose` | Show full command output including stdout/stderr |
| `--quiet` | Show summary only, suppress per-target output |
| `--no-color` | Disable ANSI color codes in output |
| `--only-preflight-checks` | Run connectivity checks (SSH, kubectl) and exit |
| `--force-no-preflight-checks` | Skip preflight checks and collect immediately |
| `--only-through-kubernetes` | Only run kubectl-based targets, skip all SSH-dependent ones |
| `--dry-run` | Show what commands would be executed without running them |

Exit codes: 0 (success), 1 (target failures), 2 (config error), 3 (preflight failed).

### Step 5 Upload Results

The operator returns to the browser and either pastes or uploads the JSONL file. Each line in the file is a JSON object with this structure:

```json
{
    "path": "databases/cassandra/cluster_status",
    "value": "UN",
    "unit": "",
    "description": "All Cassandra nodes are Up/Normal",
    "raw_output": "Datacenter: datacenter1\n=======================\n...",
    "metadata": {
        "commands": ["nodetool status"],
        "duration_seconds": 2.5
    }
}
```

Fields:

| Field | Description |
|-------|-------------|
| `path` | Hierarchical identifier using `/` separators (e.g. `kubernetes/nodes/count`, `vm/datanode1/disk_usage`) |
| `value` | The extracted metric a number, string, or boolean |
| `unit` | Unit of measurement (e.g. `%`, `Gi`, `nodes`, `pods`) empty string if not applicable |
| `description` | Human-readable explanation of what was measured |
| `raw_output` | The full terminal output of the command that produced this data point |
| `metadata` | Execution metadata: commands run, duration, host, etc. |

The file also contains a `GatheringConfig` line with the configuration used during collection (Wire version, feature flags, timestamps), which the UI displays in a Config tab.

### Step 6 Report

The UI runs the JSONL data through 172 checker classes that evaluate each data point as **healthy**, **warning**, **unhealthy**, **not_applicable**, or **gather_failure**. The results are displayed as:

- **Summary cards** total checks, healthy count, warning count, unhealthy count
- **Interactive tree table** check results grouped hierarchically by category (e.g. all Cassandra checks under "Cassandra", all Kubernetes checks under "Kubernetes")
- **Data points tree** raw data points grouped by path prefix
- **Config tab** the gathering configuration, Wire version, and deployment feature flags
- **Expandable details** clicking the eye icon on any row reveals a panel showing raw command output and execution metadata
- **Recommendations** unhealthy or warning items include actionable text explaining what to do
- **Port connectivity matrix** network reachability between nodes with SVG diagrams

The report can also be exported as a PDF.

## Data Point Categories

The gatherer collects data across these categories (117 target collectors):

| Category | What's checked |
|----------|----------------|
| **Host** | Disk usage, memory, CPU count, load average, uptime, NTP sync |
| **Kubernetes** | Node count and status, pod health, TLS certificates, ingress resources, metrics API, K8s version, container runtime, etcd health, PVC status, restart counts, helm chart versions |
| **VMs** | Per-VM disk usage, memory usage, load average (for every kubenode, datanode, and the asset host) |
| **Cassandra** | Cluster status (Up/Normal), node count, NTP sync, keyspaces, Spar IDP/tables, data disk usage |
| **Elasticsearch** | Cluster health (green/yellow/red), node count, shard count, read-only mode detection |
| **PostgreSQL** | Repmgr replication status and lag, node count (primary + standbys), version |
| **MinIO** | Network health, drive status, erasure health, bucket count, version |
| **RabbitMQ** | Cluster status, node count, queue depth, queue persistence, alarms, version |
| **Redis** | Pod running status, maxmemory configuration, memory eviction policy |
| **Wire Services** | Health and replica count for each service: brig, galley, cannon, cargohold, gundeck, spar, nginz, background-worker, sftd, coturn, webapp, team-settings, account-pages |
| **Config Validation** | JSON Schema validation of service ConfigMaps (brig, galley, gundeck, cannon, cargohold, spar, background-worker, smallstep) against Wire version schemas (5.22 through 5.27) |
| **Helm Config** | Feature flag completeness, database host consistency, ingress proxy protocol, SMS/SMTP placeholder detection, deeplink config, service log levels |
| **Federation** | Cross-service federation domain consistency, brig domain matching cluster |
| **MLS** | MLS readiness, E2EI validation, removal key configuration |
| **DNS** | Subdomain resolution, email DNS records (SPF, DKIM, DMARC) |
| **Network** | Port connectivity between nodes, SFTd reachability, TURN server connectivity |
| **TLS** | Certificate validity and expiration |
| **Security** | Default credentials, exposed endpoints, secret presence |
| **Operations** | Backup freshness, log rotation, monitoring stack, SMTP service |
| **OS** | Kubenode NTP sync, unprivileged port start, OS version matching |
| **Migrations** | Database migration status |

## Checker Rules

Each data point is evaluated by a TypeScript checker class against threshold rules. Examples:

- Disk usage > 85% = **unhealthy**, > 70% = **warning**
- Load average > 2x CPU count = **unhealthy**, > 1x = **warning**
- Memory usage > 90% = **unhealthy**, > 80% = **warning**
- Elasticsearch cluster health yellow = **warning**, red = **unhealthy**
- PostgreSQL replication status != "healthy" = **unhealthy**
- Wire service not healthy = **unhealthy**
- Wire service < 2 replicas = **warning**
- Kubernetes nodes not all Ready = **unhealthy**
- NTP not synchronized = **warning**
- ConfigMap schema validation failure = **unhealthy**
- RabbitMQ alarms active = **unhealthy**
- Redis maxmemory not configured = **warning**
- Coturn memory limits missing = **warning**

## Development

```bash
# Install frontend dependencies
cd ui && npm install

# Run dev server
cd .. && npm run dev

# Or directly
cd ui && npx vite

# Run Python tests
python3 src/test/run_tests.py
```

The dev server runs on `http://localhost:5173` by default.

---

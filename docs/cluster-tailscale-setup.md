# Cluster Tailscale Setup

Connect Jerry (the cluster) to the Clade's Tailscale mesh VPN. Because we have no root access on the cluster and can't run long-lived processes on login nodes, Tailscale runs inside SLURM jobs using **userspace networking mode**.

> **Jerry is intermittently available.** He's only reachable via Tailscale while a SLURM job is running. When the job ends or is cancelled, Jerry goes offline.

## Prerequisites

- A [Tailscale account](https://tailscale.com) (the Clade's tailnet)
- A **reusable auth key** from [Tailscale admin](https://login.tailscale.com/admin/settings/keys):
  - Type: **Reusable** (the key will be used across multiple SLURM jobs)
  - Ephemeral: **Yes** (recommended — node auto-deregisters when it disconnects)
  - Expiry: Set a long expiry or regenerate as needed
- SSH access to the cluster login node

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Tailnet (100.x.y.z)                                    │
│                                                          │
│  Mac (Doot)       masuda (Oppy)      cluster (Jerry)    │
│  100.127.78.26    100.71.57.52       100.x.y.z          │
│                                       ↑                  │
│                                       │ SLURM job        │
│                                       │ (userspace mode)  │
└─────────────────────────────────────────────────────────┘
```

**How userspace networking works:**
- `tailscaled` runs without root, using a SOCKS5 proxy for outbound traffic
- Incoming connections to the Tailscale IP are automatically forwarded to localhost
- A service listening on `localhost:8080` becomes reachable at `100.x.y.z:8080` from other tailnet nodes
- Outbound connections from the cluster need the SOCKS5 proxy (`localhost:1055`)

## One-Time Setup

Run this once on the cluster login node. It downloads Tailscale, stores your auth key, and verifies authentication.

```bash
# Clone the clade repo if you haven't already
git clone https://github.com/dunni3/clade.git ~/clade

# Run the setup script
bash ~/clade/deploy/cluster-tailscale-setup.sh
```

The script will:
1. Prompt for your Tailscale auth key (or pass it with `--authkey tskey-auth-XXXXX`)
2. Download the latest stable Tailscale binary to `~/.local/bin/tailscale/`
3. Create state directories at `~/.local/share/tailscale/`
4. Save the auth key to `~/.tailscale-authkey` (mode 600)
5. Run a quick auth test and report the Tailscale IP
6. Shut down the test daemon

## Starting Tailscale

Submit a SLURM job that keeps Tailscale running:

```bash
bash ~/clade/deploy/cluster-tailscale-start.sh
```

This will:
1. Submit the Tailscale job to the `dept_cpu` partition (24-hour walltime)
2. Wait for authentication to complete
3. Report Jerry's Tailscale IP

Once the IP is reported, Jerry is reachable from any other tailnet node.

## Stopping Tailscale

```bash
bash ~/clade/deploy/cluster-tailscale-start.sh --stop
```

This cancels the SLURM job. Tailscale shuts down cleanly via the SIGTERM trap.

## Checking Status

```bash
# Is the SLURM job running?
squeue --me --name=tailscale

# What's Jerry's current Tailscale IP?
cat ~/.local/share/tailscale/current-ip

# Check the job log
cat tailscale-<JOB_ID>.log
```

## Connectivity Test

From another tailnet node (e.g., masuda):

```bash
# Ping Jerry's Tailscale IP
ping 100.x.y.z

# SSH (if SSH is available on the compute node)
ssh 100.x.y.z
```

From the cluster (outbound through Tailscale):

```bash
# Use the SOCKS5 proxy for outbound connections
curl --proxy socks5h://localhost:1055 http://100.71.57.52:8080
```

## File Locations

| What | Path |
|------|------|
| Tailscale binaries | `~/.local/bin/tailscale/` |
| State file | `~/.local/share/tailscale/tailscaled.state` |
| Socket | `~/.local/share/tailscale/tailscaled.sock` |
| Auth key | `~/.tailscale-authkey` |
| Current IP | `~/.local/share/tailscale/current-ip` |
| Job logs | `tailscale-<JOB_ID>.log` (in submission directory) |

## Troubleshooting

### Job pending for too long
The `dept_cpu` partition may be busy. Check queue status:
```bash
squeue --partition=dept_cpu
```

### "tailscaled failed to start"
- Check if the socket file already exists from a previous run: `rm -f ~/.local/share/tailscale/tailscaled.sock`
- Check if another Tailscale process is running: `ps aux | grep tailscaled`

### Authentication fails
- Verify your auth key hasn't expired: check [Tailscale admin](https://login.tailscale.com/admin/settings/keys)
- Generate a new key and update `~/.tailscale-authkey`
- Make sure the key is **reusable** (single-use keys only work once)

### Can't reach Jerry from other nodes
- Confirm the SLURM job is running: `squeue --me --name=tailscale`
- Check the job log for errors
- Verify both nodes are on the same tailnet: run `tailscale status` on the other node

### Tailscale IP changed
With ephemeral keys, the node gets a new IP each time it connects. Check `~/.local/share/tailscale/current-ip` for the latest. Consider using [MagicDNS](https://tailscale.com/kb/1081/magic-dns) hostnames instead of raw IPs.

### Job keeps dying
- Check the log: `cat tailscale-<JOB_ID>.log`
- If `tailscaled` crashes immediately, try running it manually on the login node briefly to see the error
- Ensure the binary architecture matches (should be amd64 for the cluster)

## How This Integrates with the Clade

When the Tailscale SLURM job is running, Jerry is a full member of the tailnet:

- **Doot** (Mac) and **Oppy** (masuda) can reach Jerry at his Tailscale IP
- Services Jerry runs on localhost are accessible to the whole tailnet
- Jerry can reach other tailnet nodes via the SOCKS5 proxy at `localhost:1055`

Since Jerry is intermittent, the Clade should handle him being offline gracefully. The `cluster-tailscale-start.sh` script makes it easy to bring him back online whenever needed.

### Ember + Tailscale

The Ember server (HTTP-based task execution) relies on Tailscale for connectivity. When you run `clade setup-ember <name>`, the CLI auto-detects the brother's Tailscale IP and stores it as `ember_host` in `clade.yaml`. This means:

- **Health checks** (`clade doctor`) and the future **Conductor** reach Embers via the Tailscale mesh
- **Firewalls are bypassed** — university networks that block arbitrary ports over the public internet are transparent to Tailscale
- If Tailscale is not available, `setup-ember` falls back to the SSH hostname

For brothers on SLURM clusters, the Ember server would also need to run inside the SLURM job (alongside Tailscale). This is not yet automated — Phase 1 targets always-on machines like masuda.

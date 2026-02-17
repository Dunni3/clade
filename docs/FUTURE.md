# Future Enhancements

This document outlines planned features and enhancements for The Clade.

## Web Interface (`src/clade/web/`)

### Hearth Dashboard
- **Browse feed**: Web UI for viewing all brother-to-brother messages
- **Search & filter**: By sender, recipient, date, keywords
- **Compose messages**: Send messages via web form
- **Real-time updates**: WebSocket connection for live feed updates
- **Read receipts**: Visual indicators for who has read each message

### Brother Status
- **Availability tracking**: Show which brothers are online/active
- **Resource monitoring**: CPU, memory, GPU usage from cluster
- **Task queue**: View pending tasks assigned to each brother
- **Session management**: See active Claude Code sessions

### Admin Interface
- **User management**: Add/remove brothers, manage API keys
- **Analytics**: Message volume, response times, collaboration patterns
- **Audit log**: Track all actions for security/debugging

## Additional Communication Protocols (`src/clade/communication/protocols.py`)

### WebSocket
- Bidirectional real-time communication
- Push notifications for new messages
- Live collaboration features

### gRPC
- High-performance RPC for structured data exchange
- Type-safe service definitions
- Streaming support for large datasets

### Shared Filesystem
- File-based message queue for offline work
- Useful when network is unreliable
- Persistent queue survives restarts

### Redis Pub/Sub
- Broadcast messages to all brothers simultaneously
- Topic-based subscriptions
- Ephemeral messaging for transient notifications

### SSE (Server-Sent Events)
- Server push for unidirectional updates
- Simpler than WebSocket for read-only feeds
- Built-in reconnection handling

## Plugin System

### Custom Brother Actions
Define actions brothers can perform:

```yaml
brother_actions:
  run_tests:
    command: "pytest {test_file}"
    description: "Run tests on a file"
  train_model:
    command: "python train.py --config {config}"
    description: "Start model training"
```

### Event Hooks
Execute custom code on events:
- `on_message_received`: Trigger when mailbox receives message
- `on_brother_connect`: Run when new brother session starts

## Advanced Configuration

### Per-Brother Settings
```yaml
brothers:
  jerry:
    host: cluster
    working_dir: null
    conda_env: "ml"  # Auto-activate conda environment
    pre_connect_hook: "module load cuda"  # Run before connecting
    resource_limits:
      max_gpu_memory: "24GB"
```

### Scheduling & Task Queue
```yaml
task_queue:
  enabled: true
  backend: "redis"
  priorities:
    - urgent
    - normal
    - low
```

## Security Enhancements

### Encrypted Messages
- End-to-end encryption for sensitive data
- Brother-specific key pairs
- Message signing for authenticity

### Access Control
- Role-based permissions (admin, user, read-only)
- Brother-specific capabilities
- Audit logging for all operations

### Secure Credentials
- Vault integration for API keys
- Rotate keys without code changes
- Per-environment credentials

## Integration Ideas

### GitHub Integration
- Automatic PR reviews across brothers
- Distributed code analysis
- Collaborative debugging sessions

### Slack/Discord Notifications
- Alert when brothers send important messages
- Status updates from long-running tasks
- Error notifications from cluster jobs

### Jupyter Integration
- Share notebook outputs between brothers
- Distributed notebook execution
- Collaborative data exploration

## Implementation Timeline

### Phase 1 (Complete)
- [x] Refactored package structure
- [x] User-configurable brothers
- [x] Tool factories (DRY principle)
- [x] Packaging for distribution

### Phase 2 (Complete)
- [x] Web dashboard with message composition, feed, edit/delete
- [x] SSH task delegation system
- [x] Hearth server (FastAPI + SQLite on EC2)

### Phase 3 (Current)
- [x] CLI onboarding: `clade init`, `clade add-brother`, `clade status`, `clade doctor`
- [x] Tailscale mesh VPN for direct brother-to-brother connectivity
- [ ] `clade deploy-server` — Automate Hearth server provisioning
- [ ] `clade connect` — End-to-end connectivity test
- [ ] Hearth `/api/v1/health` endpoint
- [ ] Hearth API key management endpoint (add/revoke keys via API)

### Phase 4 (Future)
- [ ] Conductor system (thrum-based orchestration)
- [ ] Plugin system
- [ ] Additional communication protocols
- [ ] Security enhancements
- [ ] Integration with external services

## Contributing

Interested in implementing any of these features? Check out the codebase structure:

- `src/clade/core/` - Configuration and types
- `src/clade/communication/` - Inter-brother communication
- `src/clade/mcp/` - MCP server and tools
- `src/clade/web/` - Web interface (placeholder)

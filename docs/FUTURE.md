# Future Enhancements

This document outlines planned features and enhancements for terminal-spawner.

## Web Interface (`src/terminal_spawner/web/`)

### Mailbox Dashboard
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

## Additional Communication Protocols (`src/terminal_spawner/communication/protocols.py`)

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

## Cross-Platform Support

### Linux/Windows Terminal Spawning
Currently terminal spawning only works on macOS via AppleScript. Future work:

- **Linux**: Use `xdg-terminal` or direct terminal emulator commands
- **Windows**: PowerShell scripts for Terminal, ConEmu, etc.
- **Platform detection**: Auto-select appropriate implementation

Reference: `src/terminal_spawner/terminal/apps.py` has protocol-based design ready for additional implementations.

## Plugin System

### Custom Terminal Apps
Allow users to define custom terminal applications:

```yaml
custom_terminals:
  kitty:
    command_template: "kitty -e {command}"
  alacritty:
    command_template: "alacritty -e {command}"
```

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
- `on_terminal_spawn`: Hook into terminal spawning

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

### Phase 1 (Current - v0.2.0)
✅ Refactored package structure
✅ User-configurable brothers
✅ Tool factories (DRY principle)
✅ Packaging for distribution

### Phase 2 (Next - v0.3.0)
- [ ] Basic web dashboard (read-only feed)
- [ ] WebSocket support for real-time updates
- [ ] Cross-platform terminal spawning (Linux)

### Phase 3 (v0.4.0)
- [ ] Full web UI with message composition
- [ ] Task queue system
- [ ] Advanced brother configuration

### Phase 4 (v0.5.0+)
- [ ] Plugin system
- [ ] Additional communication protocols
- [ ] Security enhancements
- [ ] Integration with external services

## Contributing

Interested in implementing any of these features? Check out the codebase structure:

- `src/terminal_spawner/core/` - Configuration and types
- `src/terminal_spawner/terminal/` - Terminal spawning logic
- `src/terminal_spawner/communication/` - Inter-brother communication
- `src/terminal_spawner/mcp/` - MCP server and tools
- `src/terminal_spawner/web/` - Web interface (placeholder)

Each module is designed with extensibility in mind. The protocol-based abstractions
(`TerminalApp`, etc.) make it easy to add new implementations.

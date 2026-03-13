# Losshound

Lightweight Windows network diagnosis tool that continuously monitors connectivity and determines the most likely cause of network issues.

Losshound identifies whether failures originate from your **LAN**, **router/gateway**, **ISP/WAN**, **DNS**, or **upstream routing** — and tells you in plain language.

## Features

- **Automatic gateway detection** — finds your default gateway automatically
- **Continuous monitoring** — ping, DNS, and route checks on configurable intervals
- **Rule-based diagnosis** — transparent fault-domain inference with adjustable thresholds
- **Tracks key metrics** — packet loss, latency, jitter, DNS resolution time, route changes
- **Dark-themed GUI** — clean, compact PySide6 interface with dashboard, history, and route views
- **CLI mode** — run from the terminal with `--cli` flag
- **Export reports** — save diagnostic reports as TXT or JSON
- **Local storage** — SQLite-based history with automatic pruning
- **No admin required** — uses standard OS tools (ping, tracert, ipconfig)
- **No telemetry** — fully offline, no data collection

## Screenshots

*Screenshots to be added*

## Installation

### From source

```bash
# Clone the repository
git clone https://github.com/NoSelection/Losshound.git
cd Losshound

# Create a virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m losshound
```

### Requirements

- Python 3.11+
- Windows 10/11
- PySide6

## Usage

### GUI mode (default)

```bash
python -m losshound
```

### CLI mode

```bash
python -m losshound --cli
```

### Options

```
--cli              Run in CLI mode (no GUI)
--config PATH      Path to configuration file
--log-level LEVEL  Logging level (DEBUG, INFO, WARNING, ERROR)
```

## Configuration

Configuration is stored in `%LOCALAPPDATA%\Losshound\config.json`. Default values are used if no config file exists.

You can also edit settings through the GUI's Settings tab.

### Key settings

| Setting | Default | Description |
|---------|---------|-------------|
| `ping_interval_seconds` | 30 | How often to run ping checks |
| `dns_interval_seconds` | 60 | How often to run DNS checks |
| `route_interval_seconds` | 300 | How often to run tracert |
| `public_ping_targets` | 1.1.1.1, 8.8.8.8 | IPs to ping for WAN testing |
| `dns_test_hostnames` | google.com, chatgpt.com | Domains to resolve for DNS testing |
| `history_retention_hours` | 24 | How long to keep history |

### Diagnosis thresholds

| Threshold | Default | Description |
|-----------|---------|-------------|
| `gateway_loss_threshold` | 20% | Loss % to flag gateway issues |
| `public_loss_threshold` | 20% | Loss % to flag WAN issues |
| `dns_failure_threshold` | 50% | DNS failure rate to flag DNS issues |
| `latency_warning_ms` | 150 | Latency to flag as elevated |
| `jitter_warning_ms` | 50 | Jitter to flag as elevated |
| `route_change_sensitivity` | 3 | Route changes in window to flag instability |

## Architecture

```
src/losshound/
├── app.py              # Application entry point
├── core/
│   ├── config.py       # Configuration management
│   ├── diagnosis.py    # Rule-based diagnosis engine
│   ├── dns_checks.py   # DNS resolution testing
│   ├── gateway.py      # Default gateway detection
│   ├── logger.py       # Logging setup
│   ├── models.py       # Data models (dataclasses)
│   ├── ping.py         # Subprocess ping wrapper
│   ├── route_monitor.py # Tracert wrapper and route diffing
│   └── scheduler.py    # Background test scheduler (QThread)
├── storage/
│   └── history.py      # SQLite persistence
├── gui/
│   ├── main_window.py  # Main window with tabs
│   ├── dashboard.py    # Dashboard tab
│   ├── history_tab.py  # History/events tab
│   ├── route_tab.py    # Route details tab
│   ├── settings_tab.py # Settings tab
│   ├── export_tab.py   # Export/report tab
│   ├── theme.py        # Dark theme stylesheet
│   └── widgets.py      # Reusable widgets
├── cli/
│   └── runner.py       # CLI mode runner
└── utils/
    └── formatting.py   # Display helpers
```

### Data flow

1. **Scheduler** (background thread) runs tests on timers
2. **Gateway**, **Ping**, **DNS**, and **Route** modules collect observations
3. **Diagnosis engine** analyzes recent observations with rule-based logic
4. Results are stored in **SQLite** and emitted to the **GUI** via Qt signals

### Diagnosis logic

The engine uses a priority-ordered rule cascade:

1. Gateway unreachable → **LAN issue**
2. Gateway OK, public IPs unreachable → **ISP/WAN issue**
3. Gateway OK, public IPs OK, DNS failing → **DNS issue**
4. Route path unstable → **Upstream route issue**
5. Sporadic loss bursts → **Intermittent instability**
6. Everything OK → **Healthy**

## Building

### Development

```bash
pip install -r requirements-dev.txt
pytest
```

### Packaging with PyInstaller

```bash
pip install pyinstaller
pyinstaller --name Losshound --windowed --add-data "config.default.json;." src/losshound/app.py
```

The built application will be in `dist/Losshound/`.

## Data storage

- **History database**: `%LOCALAPPDATA%\Losshound\history.db`
- **Configuration**: `%LOCALAPPDATA%\Losshound\config.json`
- **Logs**: `%LOCALAPPDATA%\Losshound\losshound.log`

## Roadmap

- [ ] System tray support with minimize-to-tray
- [ ] Alerts when diagnosis status changes
- [ ] Dark/light theme toggle
- [ ] CSV export
- [ ] Route diff viewer (side-by-side comparison)
- [ ] Configurable alert sounds
- [ ] Multi-language ping output parsing

## Known limitations

- Ping and tracert output parsing assumes English locale (forces codepage 437)
- Tracert checks are slow (30-90 seconds) and run on a longer interval
- VPN connections may confuse gateway detection
- No IPv6 support currently

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Submit a pull request

## License

MIT License. See [LICENSE](LICENSE) for details.

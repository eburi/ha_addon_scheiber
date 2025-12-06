# Development Tasks

This project uses [Poe the Poet](https://poethepoet.natn.io/) for task automation.

## Setup

Install development dependencies:
```bash
cd scheiber/src
source .venv/bin/activate  # or: . .venv/bin/activate
pip install pytest black isort poethepoet
```

## Available Tasks

Run tasks from the project root using `poe <task>` or `scheiber/src/.venv/bin/poe <task>`:

### Testing
```bash
poe test              # Run all tests
poe test-coverage     # Run tests with coverage report
```

### Code Formatting
```bash
poe format            # Format code with black and isort
poe check-format      # Check formatting without changes
poe imports           # Organize imports
poe check-imports     # Check import organization
```

### Quality Checks
```bash
poe lint              # Run linting checks
poe check             # Run all checks (format, imports, tests)
```

### Development Tools
```bash
poe run-bridge              # Run MQTT bridge (info level)
poe run-bridge-debug        # Run MQTT bridge (debug level)
poe canlistener can1        # Run CAN listener on can1
poe analyser -i can1        # Run interactive analyzer on can1
poe bloc9-status can1 10    # Analyze Bloc9 #10 on can1
```

### Utilities
```bash
poe clean             # Remove Python cache files
poe install           # Install production dependencies
poe install-dev       # Install development dependencies
```

## Quick Start

```bash
# Format code before committing
poe format

# Run all checks
poe check

# Run specific tool
poe canlistener can1
```

## VS Code Integration

The project is configured to use the virtualenv at `scheiber/src/.venv`. 
VS Code will automatically use black for formatting and isort for organizing imports on save.

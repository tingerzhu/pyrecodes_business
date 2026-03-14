# pyrecodes
Software for regional recovery simulation and resilience assessment of the built environment based on the iRe-CoDeS framework.

For more details, please visit: https://nikolablagojevic.github.io/pyrecodes/html/usage/what_is_pyrecodes.html

## Installation

To set up the pyrecodes environment with all required dependencies, run the setup script:

```bash
./setup.sh
```

The setup script will:
- Create and activate a virtual environment 
- Install Python dependencies from requirements.txt
- Handle problematic packages (rewet, wntrfr) with appropriate fallback strategies
- Set up integration with third-party infrastructure simulators

**Note:** Make sure you have Python 3.8+ installed before running the setup script. On macOS, you may need to install Xcode Command Line Tools for some dependencies.

# YaneuraOu Python Wrapper

A Python wrapper for the YaneuraOu shogi engine's legal move generation functionality, implemented using `pybind11`. This module allows Python programs to efficiently generate legal moves from a given shogi position (SFEN string).

## Features

-   Generate all legal moves from an SFEN position.
-   For each move, get the `from` square, `to` square, and the SFEN string of the position after the move.
-   High performance by directly calling YaneuraOu's C++ move generation logic.
-   Installable via `pip`.

## Installation

```bash
# First, ensure you have Git and CMake installed.
# Clone this repository (including YaneuraOu as a submodule)
git clone --recursive https://github.com/yaneuraou/yaneuraou-python-wrapper.git # Replace with actual repo if created
cd yaneuraou-python-wrapper

# Install the Python package
pip install .
```

## Usage

```python
import yaneuraou_wrapper

# Example SFEN for initial position
sfen = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"

# Get legal moves information
moves_info = yaneuraou_wrapper.get_legal_moves_info(sfen)

for info in moves_info:
    print(f"Move: {info['usi']}, From: {info['from']}, To: {info['to']}")
    print(f"  SFEN after move: {info['sfen']}")
```

## Original Project Reference

This Python wrapper heavily relies on the high-performance C++ move generation and position representation logic from the **YaneuraOu Shogi Engine**.

-   **YaneuraOu GitHub Repository**: [https://github.com/yaneuraou/YaneuraOu](https://github.com/yaneuraou/YaneuraOu)

We express our deepest gratitude to the Yaneuraou development team for their outstanding work.

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**.
This is due to its direct incorporation and linking with the YaneuraOu source code, which is also licensed under GPLv3.

You can find a copy of the license text in the `COPYING` file or at [https://www.gnu.org/licenses/gpl-3.0.en.html](https://www.gnu.org/licenses/gpl-3.0.en.html).
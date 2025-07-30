

# AI Arduino IDE

A modern, cross-platform desktop IDE for Arduino and microcontroller development, featuring AI-powered code generation, auto library installation, compilation, direct uploading, wiring suggestions, and integrated serial monitoring—all in a user-friendly graphical interface.

## Table of Contents

- [Description](#description)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Installation](#installation-instructions)
- [Usage](#usage)
- [Supported Boards](#supported-boards)
- [Contributing](#contributing)
- [License](#license)


## Description

**AI Arduino IDE** accelerates microcontroller development by integrating advanced AI code generation with a streamlined Arduino workflow. Users can generate code from plain English prompts, auto-install required libraries, compile and upload sketches directly to their boards, and even receive pin-by-pin wiring diagrams. The built-in serial monitor and project management tools make it ideal for hobbyists, educators, and embedded professionals alike.

## Features

- **AI Code Generation:**
Instantly generate Arduino C++ code from natural language descriptions. Supports multiple LLM/AI providers.
- **Automatic Library Management:**
Required libraries are detected, installed, and managed automatically via Arduino CLI and direct GitHub fallback.
- **Smart Compilation with Auto-Fix:**
Code is auto-compiled and, if errors occur, iterative AI-powered fixes are applied (with logs for review).
- **Direct Board Upload:**
One-click upload to supported microcontroller boards using Arduino CLI and serial port detection.
- **Wiring Suggestion:**
Generates a detailed wiring connections table from your code—know how to build your circuit instantly.
- **Project Management:**
Create, open, edit, and save multiple projects/sketches, all within an intuitive GUI.
- **Integrated Serial Monitor:**
Communicate with your board in real-time via the built-in serial terminal.
- **Cross-platform GUI:**
Elegant, modern, and touch-friendly desktop interface built on Python Tkinter.
- **Extensible AI Backend:**
Works with any API-accessible LLM (e.g. Google Gemini, GPT, open-source, etc.).


## Tech Stack

- **Python 3.8+**
    - Main application and GUI logic
- **Tkinter**
    - Desktop user interface
- **Arduino CLI**
    - Compilation, library, and upload backend ([arduino-cli](https://arduino.github.io/arduino-cli/latest/))
- **Google Generative AI (Gemini), OpenAI, or others**
    - Natural language code generation and refinement (configurable)
- **PySerial**
    - Serial monitor and port management
- **Requests**
    - HTTP calls for GitHub and model APIs
- **Other Python standard libraries:**
    - `subprocess`, `threading`, `os`, `sys`, etc.


## Installation Instructions

### Prerequisites

- **Python 3.8+** (https://www.python.org/downloads/)
- **Arduino CLI** ([Download and Install Guide](https://arduino.github.io/arduino-cli/latest/installation/))
- **API key for your chosen LLM provider** (e.g., Google Gemini, OpenAI, etc.)


### 1. Clone the Repository

```sh
git clone https://github.com/yourusername/ai-arduino-ide.git
cd ai-arduino-ide
```


### 2. Install Dependencies

It's recommended to use a virtual environment:

```sh
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Or manually install required packages:

```sh
pip install -U google-generativeai tinydb pyserial requests
```


### 3. Set Up Arduino CLI

- Download Arduino CLI for your platform: https://arduino.github.io/arduino-cli/latest/installation/
- Add the CLI directory to your system PATH or update the `ARDUINO_CLI_PATH` variable in the Python script/config.


### 4. Configure API Key

- Obtain an API key for your preferred AI/LLM backend (Google Gemini, OpenAI, etc.).
- Either set it via environment variable or directly inside the config section of `main.py`:

```python
API_KEY = "your_api_key_here"
```


### 5. Run the Application

```sh
python main.py
```

The graphical IDE will open.

## Usage

1. **Start the IDE.**
2. **Create a new project** or open an existing `.ino` sketch.
3. **Enter a natural language description** of the project in the prompt field (e.g., *"Blink an LED on pin 13 every second"*).
4. **Click "Generate"** to auto-generate code.
5. **Edit or review the code** in the code editor panel.
6. **Click "Save"** to store your sketch.
7. **Click "Upload"** to upload to your connected Arduino board.
8. **Use "Serial Monitor"** to see device output or communicate.
9. **Click "Wiring"** for a detailed hardware connection table.

## Supported Boards

- Arduino Uno
- Arduino Mega
- Arduino Nano
- Arduino Leonardo
- Arduino Nano Every
- Arduino Due
- Arduino MKR Zero
- ESP32 Dev
- NodeMCU 1.0 (ESP-12E)
…and easily extensible to more (edit `BOARD_OPTIONS` in the code).


## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- Bug reports and feature requests can be submitted as GitHub issues.
- PRs should follow [PEP8](https://peps.python.org/pep-0008/) and include clear, professional docstrings.


## License

This project is licensed under the MIT License.
See [LICENSE](LICENSE) for details.

> **Note:**
> This IDE is model-agnostic and can be configured to use any AI code generation provider with a compatible API.
> Your code and board connections remain local and private—you control your workflow and data at all times.




# Screenshot Answerer

This is a tool that uses Optical Character Recognition (OCR) to extract text from screenshots, then leverages AI models to provide solutions to coding problems and multiple-choice questions. The tool sends the solutions directly to you via a Telegram bot.

## Table of Contents

1.  [Features](#features)
2.  [Setup](#setup)
    *   [Prerequisites](#prerequisites)
    *   [Installation](#installation)
    *   [API Key Configuration](#api-key-configuration)
        *   [Gemini API Key](#gemini-api-key)
        *   [Telegram Bot Token](#telegram-bot-token)
    *   [User Configuration](#user-configuration)
3.  [Usage](#usage)
    *   [Hotkeys](#hotkeys)
4.  [Contributing](#contributing)
5.  [License](#license)
6.  [Support](#support)

## Features

*   **OCR Text Extraction:** Captures screenshots and extracts text using Optical Character Recognition (OCR).
*   **AI-Powered Solutions:** Leverages AI models to solve coding problems (Python only) and answer multiple-choice questions (MCQs).
*   **Telegram Integration:** Sends solutions directly to your Telegram account for convenient access.
*   **Customizable Hotkeys:** Uses hotkeys to trigger different functionalities (code generation, MCQ answering).
*   **Multi-Platform Support:** Works on Windows, macOS, and Linux.

## Setup

### Prerequisites

Before you begin, ensure you have the following installed:

*   **Python 3.9 or later:** You can download Python from [https://www.python.org/downloads/](https://www.python.org/downloads/)
*   **pip:** Python package installer (usually included with Python installations)
*   **Tesseract OCR Engine:**
    *   **Windows:** Download from [https://digi.bib.uni-mannheim.de/tesseract/](https://digi.bib.uni-mannheim.de/tesseract/) and install.  Make sure to add the Tesseract installation directory (e.g., `C:\Program Files\Tesseract-OCR`) to your system's `PATH` environment variable.
    *   **macOS:**  Install via Homebrew: `brew install tesseract`
    *   **Linux (Debian/Ubuntu):** `sudo apt update && sudo apt install tesseract-ocr`

### Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/iamsjeevan/screenshot_answerer.git
    cd screenshot_answerer
    ```

2.  **Create a virtual environment:**

    ```bash
    python3 -m venv venv
    ```

3.  **Activate the virtual environment:**

    *   **Windows:**

        ```bash
        .\venv\Scripts\activate
        ```

    *   **macOS/Linux:**

        ```bash
        source venv/bin/activate
        ```

4.  **Install the required Python packages:**

    ```bash
    pip install -r requirements.txt
    ```

### API Key Configuration

You'll need to obtain API keys for the AI model and Telegram bot.

#### Gemini API Key

1.  Go to the Google AI Studio: [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) and create a new API key.
2.  Set the `GEMINI_API_KEY` environment variable.

    *   **Method 1: Using `.env` File (Recommended)**
        *   Create a `.env` file in the project directory.
        *   Add the following line to the `.env` file, replacing `YOUR_GEMINI_API_KEY` with your actual key:

            ```
            GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
            ```

    *   **Method 2: Setting the Environment Variable Directly**
        *   **Windows (Command Prompt):**

            ```cmd
            setx GEMINI_API_KEY "YOUR_GEMINI_API_KEY"
            ```

            (Note: You may need to restart your command prompt or computer for the variable to take effect.)
        *   **Windows (PowerShell):**

            ```powershell
            $env:GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
            ```

        *   **macOS/Linux:**

            ```bash
            export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
            ```

            (For permanent setting, add this line to your shell's startup file, e.g., `~/.bashrc`, `~/.zshrc`, `~/.bash_profile`.)

#### Telegram Bot Token

1.  Create a Telegram bot by talking to the [BotFather](https://telegram.me/BotFather) on Telegram.
2.  Follow the instructions to create a new bot and obtain your bot's token.
3.  Set the `TELEGRAM_BOT_TOKEN` environment variable.  Use the same methods as described for the `GEMINI_API_KEY`.

### User Configuration

1.  Open the `main.py` file.
2.  Locate the `USER_CHAT_IDS` dictionary.
3.  Add your Telegram user ID and a descriptive name to the dictionary.
    *   **To find your Telegram User ID:**
        1.  Send the message `/start` to the Telegram bot [@silentscreenshothelperbot](https://telegram.me/silentscreenshothelperbot).
        2.  I will manually add it for security reasons.
        3.  After I added, I'll send you a message indicating you have been added, and you can check if they can get text from the screen.

    Example:

    ```python
    USER_CHAT_IDS = {
        "1": {"name": "YourName", "id": "YOUR_TELEGRAM_USER_ID"},
        # Add more users here
    }
    ```
4.  When you run the script, it will prompt you to choose a recipient from the configured users.

## Usage

1.  **Activate the virtual environment:** (If you haven't already)

    ```bash
    source venv/bin/activate  # macOS/Linux
    .\venv\Scripts\activate   # Windows
    ```

2.  **Run the script:**

    ```bash
    python main.py
    ```

3.  **Select the recipient:**  The script will prompt you to choose the recipient for the Telegram messages. Enter the corresponding number and press Enter.

4.  **Use the hotkeys:** Once the script is running, use the following hotkeys to trigger different actions:

### Hotkeys

*   **`Cmd/Ctrl + Shift + 1`:** (OCR\_CODE\_HOTKEY) Captures a screenshot, extracts text, and generates Python code to solve the problem. Sends the code as a file to Telegram.
*   **`Cmd/Ctrl + Shift + 2`:** (OCR\_MCQ\_HOTKEY) Captures a screenshot, extracts text, and answers a multiple-choice question. Sends the answer and explanation to Telegram.
*   **`Cmd/Ctrl + Shift + 3`:** (OCR\_PYTHON\_CODE\_HOTKEY) Captures a screenshot, extracts text, and generates Python code to solve the problem. *Explicitly* forces Python code generation.  Sends the code as a file to Telegram.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the [MIT License](LICENSE).

## Support

If you encounter any issues or have questions, please contact me. I'll monitor the Telegram bot [@silentscreenshothelperbot](https://telegram.me/silentscreenshothelperbot) for messages and provide assistance.

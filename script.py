import sys
import threading
import mss
import pytesseract
from pynput import keyboard
from PIL import Image
import time
import os
import json
import google.generativeai as genai
import pyperclip
from dotenv import load_dotenv
import telegram
import asyncio
from concurrent.futures import Future
import logging
from logging.handlers import RotatingFileHandler
import tempfile

# --- Load the environment variables from the .env file ---
load_dotenv()

# --- SAFE CONFIGURATION ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# --- User and Chat ID Configuration ---
# The script will ask you to choose one of these users on startup.
USER_CHAT_IDS = {
    "1": {"name": "Jeevan", "id": "7107828513"},
    "2": {"name": "Kushal", "id": "1931229819"},
    "3": {"name": "Shahbhaaz", "id": "5963030030"},
    "4":{"name": "Somnath" , "id" : "7774323731"}
}
# This global variable will be set when the script starts.
SELECTED_CHAT_ID = None
SELECTED_USER_NAME = None

# Tesseract path for Windows
if sys.platform == "win32":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Hotkey configuration
MOD_KEY = "<cmd>" if sys.platform == "darwin" else "<ctrl>"
OCR_HOTKEY = f'{MOD_KEY}+<shift>+1'
SELECTION_HOTKEY = f'{MOD_KEY}+<shift>+2'

AI_MODEL = "gemini-2.5-flash-preview-05-20"
TIME_BETWEEN_MESSAGES_SEC = 1.5 # Not strictly used, but good to keep in mind for rate limits

# --- Logging Setup ---
LOG_FILE = 'application.log'
MAX_LOG_BYTES = 5 * 1024 * 1024 # 5 MB
BACKUP_COUNT = 3 # Keep 3 old log files

logger = logging.getLogger()
logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

def handle_exception(exc_type, exc_value, exc_traceback):
    """Log any uncaught exception before program exits."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Unhandled exception caught by excepthook:", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

# --- Global Asyncio Event Loop and Bot Object ---
loop = None
telegram_bot = None
loop_thread = None

# Helper function to format hotkeys for display in logs/console
def format_hotkey_for_display(hotkey_str: str) -> str:
    """Converts internal hotkey string to user-friendly format."""
    return ' '.join(hotkey_str.replace('<','').replace('>','').split('+'))

def escape_markdown_v2(text: str) -> str:
    """Escapes characters in a string for Telegram's MarkdownV2."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    text = text.replace('\\', '\\\\')
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def get_ai_answer(input_text: str) -> str:
    """
    Sends input text to a Gemini AI model and returns a structured response
    indicating if it's an MCQ answer or code (Python/C++).
    """
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not found in .env file.")
        return "ERROR: GEMINI_API_KEY not found in .env file."

    # Determine the target programming language based on the recipient
    target_lang = "Python"
    if SELECTED_USER_NAME == "Jeevan":
        target_lang = "C++"

    # Enhanced and structured prompt for the AI
    prompt = (
        "Analyze the following problem description. Your response *must* start with either `TYPE:MCQ` or `TYPE:CODE`.\n"
        "If it is a Multiple Choice Question (MCQ):\n"
        "- Respond in the format: `TYPE:MCQ\\nANSWER:<Option Letter>` (e.g., `TYPE:MCQ\\nANSWER:A`). "
        "Do NOT include explanations, numbering, or any additional text beyond the specified format.\n"
        "If it is a programming problem:\n"
        f"- Respond in the format: `TYPE:CODE\\nLANGUAGE:{target_lang}\\nCODE:<code>`. "
        f"The `<code>` part must contain ONLY the raw {target_lang} code solution. "
        "Do NOT include any explanations, comments, introductory sentences, or markdown formatting like ```python or ```cpp.\n"
        f"Problem:\n---\n{input_text}\n---"
    )

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(AI_MODEL)
        response = model.generate_content(prompt)
        # Ensure the response is stripped of leading/trailing whitespace
        return response.text.strip()
    except Exception as e:
        logger.exception(f"Error from AI model during content generation for text: {input_text[:50]}...")
        return f"ERROR: AI generation failed: {e}"

# --- UPDATED TELEGRAM FUNCTIONS ---

async def send_telegram_message_async(message_text: str):
    """
    ASYNC function to send a simple, plain-text message via Telegram
    to the globally selected user.
    """
    if not telegram_bot or not SELECTED_CHAT_ID:
        logger.error("Telegram Bot not initialized or no user selected. Check startup.")
        return

    escaped_message = escape_markdown_v2(message_text)
    try:
        await telegram_bot.send_message(
            chat_id=int(SELECTED_CHAT_ID),
            text=escaped_message,
            parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
        )
        logger.info(f"Telegram status message sent successfully to {SELECTED_USER_NAME} ({SELECTED_CHAT_ID})!")
    except Exception as e:
        logger.exception(f"Failed to send simple Telegram message: {e}")

async def send_code_as_file_async(code_text: str, caption: str): # Removed file_extension parameter
    """
    ASYNC function to send code as a .txt file via Telegram
    to the globally selected user.
    """
    if not telegram_bot or not SELECTED_CHAT_ID:
        logger.error("Telegram Bot not initialized or no user selected. Cannot send file.")
        return

    if not code_text or not code_text.strip():
        logger.info("AI returned no code. Sending a status message instead.")
        await send_telegram_message_async("The AI did not generate any code for the given input.")
        return

    escaped_caption = escape_markdown_v2(caption)
    temp_file_path = None # Initialize outside try-block for finally
    try:
        # Use a temporary file to hold the code, always with .txt suffix
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
            temp_file.write(code_text)
            temp_file_path = temp_file.name

        logger.info(f"Sending code as a file: {temp_file_path}")

        # Send the file, always named solution.txt
        with open(temp_file_path, 'rb') as file_to_send:
            await telegram_bot.send_document(
                chat_id=int(SELECTED_CHAT_ID),
                document=file_to_send,
                filename="solution.txt", # Always send as .txt
                caption=escaped_caption,
                parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
            )
        logger.info(f"Telegram document sent successfully to {SELECTED_USER_NAME} ({SELECTED_CHAT_ID})!")

    except Exception as e:
        logger.exception("An error occurred while sending the code as a file.")
        await send_telegram_message_async(f"An internal error occurred while trying to send the code file: {e}")
    finally:
        # Clean up the temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

def run_async_task(coro):
    """Submits a coroutine to the global asyncio loop from a synchronous context."""
    if loop and loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, loop)
    else:
        logger.critical("Asyncio event loop is not running. Cannot submit task.")
        # Return a Future that's immediately done, possibly with an exception
        f = Future()
        f.set_exception(RuntimeError("Asyncio event loop not running"))
        return f

# --- UPDATED TASK FUNCTIONS ---

def process_ai_response(ai_raw_response: str):
    """
    Parses the structured AI response and dispatches the appropriate Telegram action.
    """
    if ai_raw_response.startswith("ERROR:"):
        run_async_task(send_telegram_message_async(ai_raw_response))
        return

    if ai_raw_response.startswith("TYPE:MCQ"):
        try:
            mcq_answer = ai_raw_response.split("ANSWER:", 1)[1].strip()
            if mcq_answer:
                logger.info(f"Detected MCQ. Sending answer: {mcq_answer}")
                run_async_task(send_telegram_message_async(f"MCQ Answer: {mcq_answer}"))
            else:
                logger.warning("AI returned MCQ type but no answer option found.")
                run_async_task(send_telegram_message_async("AI detected an MCQ but could not extract the answer. Please try again."))
        except IndexError:
            logger.error(f"Malformed MCQ response from AI: {ai_raw_response}")
            run_async_task(send_telegram_message_async("AI returned a malformed MCQ answer. Please review the input."))
    elif ai_raw_response.startswith("TYPE:CODE"):
        try:
            parts = ai_raw_response.split('\n')
            
            # Find LANGUAGE and CODE lines
            language = None
            code_start_index = -1
            for i, part in enumerate(parts):
                if part.startswith("LANGUAGE:"):
                    language = part.split("LANGUAGE:", 1)[1].strip()
                elif part.startswith("CODE:"):
                    code_start_index = i
            
            if language is None or code_start_index == -1:
                raise ValueError("Missing LANGUAGE or CODE section in AI response.")

            # The actual code starts on the line *after* "CODE:"
            code_text = "\n".join(parts[code_start_index + 1:]).strip()

            if not code_text:
                logger.info(f"AI returned no {language} code.")
                run_async_task(send_telegram_message_async(f"The AI did not generate any {language} code for the given input."))
                return

            caption = f"{language} code generated from input (as .txt):" # Updated caption for clarity
            logger.info(f"Detected programming problem ({language}). Sending code as .txt file.")
            run_async_task(send_code_as_file_async(code_text, caption)) # Removed file_extension argument

        except (IndexError, ValueError) as e:
            logger.error(f"Malformed CODE response from AI: {ai_raw_response}. Error: {e}")
            run_async_task(send_telegram_message_async("AI returned a malformed code answer. Please review the input."))
    else:
        logger.error(f"Unexpected AI response format: {ai_raw_response}")
        run_async_task(send_telegram_message_async("AI returned an unexpected response format. Could not process the request."))


def perform_ocr_task():
    """
    Captures a screenshot, performs OCR, gets a structured AI answer, and dispatches it.
    """
    logger.info("Hotkey %s pressed. Initiating OCR task from screenshot...", format_hotkey_for_display(OCR_HOTKEY))
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            sct_img = sct.grab(monitor)
            pil_image = Image.frombytes("RGB", sct_img.size, sct_img.rgb)

        ocr_text = pytesseract.image_to_string(pil_image)
        if not ocr_text.strip():
            logger.info("No text recognized by OCR.")
            run_async_task(send_telegram_message_async("No text was recognized from the screenshot."))
            return

        ai_raw_response = get_ai_answer(ocr_text)
        process_ai_response(ai_raw_response)

    except Exception as e:
        logger.exception("An error occurred in perform_ocr_task.")
        run_async_task(send_telegram_message_async(f"An internal error occurred during OCR task: {e}"))

def perform_selection_task():
    """
    Reads text from clipboard, gets a structured AI answer, and dispatches it.
    """
    logger.info("Hotkey %s pressed. Initiating selection task from clipboard...", format_hotkey_for_display(SELECTION_HOTKEY))
    try:
        selected_text = pyperclip.paste()
        if not selected_text.strip():
            logger.info("Clipboard is empty or contains no readable text.")
            run_async_task(send_telegram_message_async("Clipboard is empty. Please copy some text first."))
            return

        ai_raw_response = get_ai_answer(selected_text)
        process_ai_response(ai_raw_response)

    except pyperclip.PyperclipException as e:
        logger.exception(f"Failed to access clipboard: {e}.")
        run_async_task(send_telegram_message_async(f"Could not access clipboard: {e}"))
    except Exception as e:
        logger.exception("An error occurred in perform_selection_task.")
        run_async_task(send_telegram_message_async(f"An internal error occurred during selection task: {e}"))

def start_loop_in_thread(loop_obj):
    """Function to run the asyncio event loop in a separate thread."""
    asyncio.set_event_loop(loop_obj)
    loop_obj.run_forever()

def main():
    """
    Main function to initialize the script, asyncio loop, and hotkey listener.
    """
    global loop, telegram_bot, loop_thread, SELECTED_CHAT_ID, SELECTED_USER_NAME

    logger.info("Starting application initialization.")

    # --- User selection menu at startup ---
    while True:
        print("\n--- Who is the recipient for this session? ---")
        for key, user_info in USER_CHAT_IDS.items():
            print(f"  {key}) {user_info['name']}")
        choice = input("Enter the number of the recipient: ")

        if choice in USER_CHAT_IDS:
            SELECTED_CHAT_ID = USER_CHAT_IDS[choice]['id']
            SELECTED_USER_NAME = USER_CHAT_IDS[choice]['name']
            logger.info(f"Recipient for this session set to: {SELECTED_USER_NAME} (ID: {SELECTED_CHAT_ID})")
            break
        else:
            print("Invalid choice. Please try again.")

    if not all([TELEGRAM_BOT_TOKEN, GEMINI_API_KEY]):
        logger.critical("One or more variables are missing from your .env file.")
        logger.critical("Please ensure TELEGRAM_BOT_TOKEN and GEMINI_API_KEY are set.")
        return

    # --- Start the asyncio event loop in a background thread ---
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=start_loop_in_thread, args=(loop,), daemon=True)
    loop_thread.start()
    logger.info("Asyncio event loop started in a separate thread.")
    time.sleep(0.1) # Give the loop a moment to start

    # --- Initialize the Telegram bot ---
    if TELEGRAM_BOT_TOKEN:
        try:
            telegram_bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
            logger.info("Telegram Bot object initialized successfully.")
        except Exception as e:
            logger.critical(f"Failed to initialize Telegram Bot object: {e}. Messages will not be sent.", exc_info=True)
            telegram_bot = None

    if telegram_bot is None:
        logger.critical("Telegram Bot failed to initialize. Exiting.")
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        return

    # --- Setup and start the hotkey listener ---
    hotkeys_to_listen = {
        OCR_HOTKEY: perform_ocr_task,
        SELECTION_HOTKEY: perform_selection_task
    }

    logger.info("Configured hotkeys for listener:")
    for hotkey_str, callback_func in hotkeys_to_listen.items():
        logger.info(f"  - '{format_hotkey_for_display(hotkey_str)}' will trigger '{callback_func.__name__}'")

    try:
        with keyboard.GlobalHotKeys(hotkeys_to_listen) as listener:
            logger.info(f"AI Telegram Bot tool is running securely for {SELECTED_USER_NAME}.")
            logger.info("Listener is active and waiting for hotkey presses.")
            listener.join()
    except Exception as e:
        logger.critical(f"An unhandled error occurred in the pynput listener: {e}", exc_info=True)
    finally:
        if loop and loop.is_running():
            logger.info("Stopping asyncio event loop...")
            loop.call_soon_threadsafe(loop.stop)
            # Give the thread a moment to finish, but don't block indefinitely
            loop_thread.join(timeout=5)
            if loop_thread.is_alive():
                logger.warning("Asyncio loop thread did not stop gracefully.")
        logger.info("Application exited.")

if __name__ == "__main__":
    main()
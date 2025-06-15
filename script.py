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

# --- Load the environment variables from the .env file ---
load_dotenv()

# --- SAFE CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Tesseract path for Windows
if sys.platform == "win32":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Hotkey configuration
MOD_KEY = "<cmd>" if sys.platform == "darwin" else "<ctrl>"
OCR_HOTKEY = f'{MOD_KEY}+<shift>+1'
SELECTION_HOTKEY = f'{MOD_KEY}+<shift>+2'

AI_MODEL = "gemini-2.5-flash-preview-05-20"
CODE_CHAR_LIMIT_PER_PART = 3800 
TIME_BETWEEN_MESSAGES_SEC = 1.5

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
    """
    Log any uncaught exception before program exits.
    """
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
    """
    Escapes characters in a string that have special meaning in Telegram's MarkdownV2.
    This is crucial for any text that is *not* inside a pre-formatted or code block.
    """
    special_chars = [
        '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'
    ]
    
    text = text.replace('\\', '\\\\') 

    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def get_ai_answer(input_text: str) -> str:
    """
    Sends input text (either from OCR or clipboard) to a Gemini AI model
    and returns the generated Python code.
    """
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not found in .env file.")
        return "ERROR: GEMINI_API_KEY not found in .env file."
    
    prompt = f"Based on the following text, provide a Python code solution. ONLY the raw Python code. No comments or explanation.\n\nText:\n---\n{input_text}\n---"
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(AI_MODEL)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.exception(f"Error from AI model during content generation for text: {input_text[:50]}...")
        return f"Error from AI: {e}"

def split_code_into_chunks(code_text: str, max_code_chars_per_chunk: int) -> list[str]:
    """
    Splits a long string of code into fixed-size chunks.
    """
    if not code_text.strip():
        return ["No content to send."]

    chunks = []
    if len(code_text) <= max_code_chars_per_chunk:
        return [code_text]

    for i in range(0, len(code_text), max_code_chars_per_chunk):
        chunk = code_text[i:i + max_code_chars_per_chunk]
        chunks.append(chunk)
    
    return chunks

async def send_telegram_message_async(message_body: str, is_code: bool = True):
    """
    ASYNC function to send a message via Telegram.
    Can send either code (wrapped in ```) or plain text (fully escaped).
    """
    if not telegram_bot or not TELEGRAM_CHAT_ID:
        logger.error("Telegram Bot not initialized or Chat ID missing. Check .env file.")
        return

    if not message_body or not message_body.strip():
        message_body = "No content to send."
    
    final_messages_to_send = []

    if is_code:
        code_parts = split_code_into_chunks(message_body, CODE_CHAR_LIMIT_PER_PART)
        total_parts = len(code_parts)
        for i, part_content in enumerate(code_parts):
            raw_prefix = f"Part {i+1}/{total_parts}:\n"
            escaped_prefix = escape_markdown_v2(raw_prefix)
            code_block = f"```python\n{part_content}\n```"

            final_message_body = escaped_prefix + code_block
            final_messages_to_send.append(final_message_body)
    else:
        final_messages_to_send.append(escape_markdown_v2(message_body))

    for i, message_part in enumerate(final_messages_to_send):
        try:
            if len(message_part) > 4096:
                logger.warning(f"Message part {i+1}/{len(final_messages_to_send)} exceeds Telegram's 4096 char limit. Truncating.")
                message_part = message_part[:4093] + "..." 

            await telegram_bot.send_message(
                chat_id=int(TELEGRAM_CHAT_ID),
                text=message_part,
                parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
            )
            logger.info(f"Telegram message part {i+1}/{len(final_messages_to_send)} sent successfully!")
            
            if i < len(final_messages_to_send) - 1:
                await asyncio.sleep(TIME_BETWEEN_MESSAGES_SEC)
                
        except telegram.error.TimedOut as e:
            logger.error(f"Telegram API request timed out for part {i+1}/{len(final_messages_to_send)}: {e}")
        except telegram.error.TelegramError as e:
            logger.error(f"Failed to send Telegram message part {i+1}/{len(final_messages_to_send)}: {e}")
            if "Bad Request: message is too long" in str(e):
                logger.error(f"Message part was too long ({len(message_part)} chars). Review CODE_CHAR_LIMIT_PER_PART or plain text length.")
            elif "Bad Request: Can't parse entities" in str(e):
                logger.error(f"Markdown parsing error in part {i+1}/{len(final_messages_to_send)}. Ensure all text is correctly escaped. Error: {e}")
            else:
                logger.error(f"Other Telegram API error for part {i+1}/{len(final_messages_to_send)}: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred sending Telegram message part {i+1}/{len(final_messages_to_send)}.")

def run_async_task(coro):
    """Submits a coroutine to the global asyncio loop from a synchronous context."""
    if loop and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future 
    else:
        logger.error("Asyncio event loop is not running. Cannot submit task. Attempting synchronous fallback.")
        try:
            asyncio.run(coro) 
        except RuntimeError as e:
             logger.critical(f"Could not run async task (fallback failed): {e}. Is the loop thread initialized and running?")


def perform_ocr_task():
    """
    Captures a screenshot, performs OCR, gets an AI answer, and sends it via Telegram.
    """
    logger.info("Hotkey %s pressed. Initiating OCR task from screenshot...", format_hotkey_for_display(OCR_HOTKEY)) # NEW LOG
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[0] 
            sct_img = sct.grab(monitor) 
        
        pil_image = Image.frombytes("RGB", sct_img.size, sct_img.rgb) 
        ocr_text = pytesseract.image_to_string(pil_image)
        
        if not ocr_text.strip():
            logger.info("No text recognized by OCR.")
            run_async_task(send_telegram_message_async("No text recognized from screenshot.", is_code=False))
            return
        
        ai_answer = get_ai_answer(ocr_text)
        run_async_task(send_telegram_message_async(ai_answer, is_code=True))
    except Exception as e:
        logger.exception("An error occurred in perform_ocr_task.")
        run_async_task(send_telegram_message_async(f"An internal error occurred during OCR task: {e}", is_code=False))

def perform_selection_task():
    """
    Reads text from the clipboard, gets an AI answer, and sends it via Telegram.
    """
    logger.info("Hotkey %s pressed. Initiating selection task from clipboard...", format_hotkey_for_display(SELECTION_HOTKEY)) # NEW LOG
    try:
        selected_text = pyperclip.paste()
        
        if not selected_text.strip():
            logger.info("Clipboard is empty or contains no readable text.")
            run_async_task(send_telegram_message_async("Clipboard is empty. Please copy text first.", is_code=False))
            return
        
        ai_answer = get_ai_answer(selected_text)
        run_async_task(send_telegram_message_async(ai_answer, is_code=True))
    except pyperclip.PyperclipException as e:
        logger.exception(f"Failed to access clipboard: {e}. Ensure xclip/xsel is installed on Linux or a GUI clipboard is available.")
        run_async_task(send_telegram_message_async(f"Could not access clipboard: {e}", is_code=False))
    except Exception as e:
        logger.exception("An error occurred in perform_selection_task.")
        run_async_task(send_telegram_message_async(f"An internal error occurred during selection task: {e}", is_code=False))

# Function to run the asyncio event loop in a separate thread
def start_loop_in_thread(loop_obj):
    asyncio.set_event_loop(loop_obj)
    loop_obj.run_forever()

def main():
    """
    Main function to initialize the script, asyncio loop, and hotkey listener.
    """
    global loop, telegram_bot, loop_thread

    logger.info("Starting application initialization.") # Initial log

    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY]):
        logger.critical("One or more variables are missing from your .env file.")
        logger.critical("Please ensure TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, and GEMINI_API_KEY are set.")
        return

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=start_loop_in_thread, args=(loop,), daemon=True)
    loop_thread.start()
    logger.info("Asyncio event loop started in a separate thread.")

    time.sleep(0.1) 

    if not telegram_bot and TELEGRAM_BOT_TOKEN:
        try:
            telegram_bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
            logger.info("Telegram Bot object initialized successfully.")
        except Exception as e:
            logger.critical(f"Failed to initialize Telegram Bot object: {e}. Messages will not be sent.", exc_info=True)
            telegram_bot = None

    if telegram_bot is None:
        logger.critical("Telegram Bot object failed to initialize. Cannot send messages. Exiting.")
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1)
        return

    hotkeys_to_listen = {
        OCR_HOTKEY: perform_ocr_task,
        SELECTION_HOTKEY: perform_selection_task
    }

    # NEW: Log which hotkeys are being listened for
    logger.info("Configured hotkeys for listener:")
    for hotkey_str, callback_func in hotkeys_to_listen.items():
        logger.info(f"  - '{format_hotkey_for_display(hotkey_str)}' will trigger '{callback_func.__name__}'")

    try:
        with keyboard.GlobalHotKeys(hotkeys_to_listen) as listener:
            logger.info("AI Telegram Bot tool is running securely (using .env).")
            logger.info("Listener is active and waiting for hotkey presses.")
            logger.info("Remember to send a message to your bot on Telegram first to enable it to send messages to you!")
            listener.join()
    except Exception as e:
        logger.critical(f"An unhandled error occurred in the pynput listener: {e}", exc_info=True)
    finally:
        if loop and loop.is_running():
            logger.info("Stopping asyncio event loop...")
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=5)
            if loop_thread.is_alive():
                logger.warning("Asyncio loop thread did not stop gracefully.")
        logger.info("Application exited.")


if __name__ == "__main__":
    main()
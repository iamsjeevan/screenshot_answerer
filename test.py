from PIL import Image
from dotenv import load_dotenv
from concurrent.futures import Future
from logging.handlers import RotatingFileHandler
import os
import sys
import logging
import keyboard
import asyncio
import threading
import tempfile
import pyscreenshot as ImageGrab
import time
import google.generativeai as genai
from telegram import Bot
from telegram.error import TelegramError

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
    "3": {"name": "Shahbhaaz", "id": "5963030030"}
}
# This global variable will be set when the script starts.
SELECTED_CHAT_ID = None
SELECTED_USER_NAME = None

# Tesseract path for Windows
if sys.platform == "win32":
    # Windows-specific configuration if needed
    pass

# Hotkey configuration
MOD_KEY = "cmd" if sys.platform == "darwin" else "ctrl"
OCR_HOTKEY = f'{MOD_KEY}+shift+1'
SELECTION_HOTKEY = f'{MOD_KEY}+shift+2'
EXIT_HOTKEY = 'esc' # Hotkey to exit the script gracefully

AI_MODEL = "gemini-2.5-flash-preview-05-20"
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
    if issubclass(exc_type, KeyboardInterrupt):
        # Let the default handler handle keyboard interrupt
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

# Set the exception handler
sys.excepthook = handle_exception

# Global variables
bot = None
loop = None
exit_event = threading.Event()

def format_hotkey(hotkey_str):
    return hotkey_str.replace('+', ' ')

def send_telegram_message(message_text):
    """Send a message via Telegram bot to the selected user."""
    try:
        future = asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id=SELECTED_CHAT_ID, text=message_text),
            loop
        )
        result = future.result(timeout=10)
        logger.info(f"Telegram status message sent successfully to {SELECTED_USER_NAME} ({SELECTED_CHAT_ID})!")
        return True
    except TelegramError as e:
        logger.error(f"Failed to send telegram message: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error sending telegram message: {str(e)}")
        return False

def process_image_with_gemini(image_path):
    """Process an image with Gemini AI and return the response."""
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(AI_MODEL)
        
        image_parts = []
        with open(image_path, "rb") as img_file:
            image_data = img_file.read()
            image_parts = [
                {
                    "mime_type": "image/png", 
                    "data": image_data
                }
            ]
        
        prompt_text = "Describe this image clearly. If it contains text, please read and extract all text accurately. If it's a question, please answer it thoroughly."
        response = model.generate_content([prompt_text, *image_parts])
        
        # Process and return the AI's response
        return response.text
        
    except Exception as e:
        logger.exception(f"Error processing image with Gemini: {str(e)}")
        return f"Error analyzing image: {str(e)}"

def perform_ocr_task():
    try:
        logger.info("Hotkey %s pressed. Initiating OCR task from screenshot...", format_hotkey(OCR_HOTKEY))
        
        # Take screenshot of the entire screen
        screenshot = ImageGrab.grab()
        
        # Save to a temporary file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            screenshot_path = temp_file.name
            screenshot.save(screenshot_path)
        
        # Send status message
        send_telegram_message(f"🔍 Analyzing screenshot...")
        
        # Process with Gemini AI
        ai_response = process_image_with_gemini(screenshot_path)
        
        # Clean up the temporary file
        try:
            os.unlink(screenshot_path)
        except:
            pass
            
        # Send the AI's response in chunks to avoid message length limits
        if ai_response:
            max_length = 4000  # Telegram message length limit
            chunks = [ai_response[i:i+max_length] for i in range(0, len(ai_response), max_length)]
            
            for i, chunk in enumerate(chunks):
                # Add continuation marker for multiple chunks
                prefix = "" if i == 0 else "(continued) "
                send_telegram_message(f"{prefix}{chunk}")
                if i < len(chunks) - 1:
                    time.sleep(TIME_BETWEEN_MESSAGES_SEC)
        else:
            send_telegram_message("❌ Failed to analyze the screenshot.")
            
    except Exception as e:
        logger.error("An error occurred in perform_ocr_task.")
        logger.exception(e)
        send_telegram_message(f"❌ Error taking screenshot: {str(e)}")

def perform_selection_task():
    try:
        logger.info("Hotkey %s pressed. Initiating task from text selection...", format_hotkey(SELECTION_HOTKEY))
        
        # This is a placeholder - in a full implementation you would
        # capture text selection from the clipboard
        send_telegram_message("Text selection feature not implemented yet.")
        
    except Exception as e:
        logger.error("An error occurred in perform_selection_task.")
        logger.exception(e)
        send_telegram_message(f"❌ Error processing text selection: {str(e)}")

def on_exit():
    """Handle cleanup when exiting the application."""
    logger.info("Exit hotkey pressed. Shutting down...")
    exit_event.set()
    # Additional cleanup if needed
    logger.info("Application terminated.")
    sys.exit(0)

def run_async_loop(loop):
    """Run the asyncio event loop in a separate thread."""
    asyncio.set_event_loop(loop)
    loop.run_forever()

def main():
    global SELECTED_CHAT_ID, SELECTED_USER_NAME, bot, loop
    
    logger.info("Starting application initialization.")
    
    # Select the user for this session
    print("\n--- Who is the recipient for this session? ---")
    for key, user in USER_CHAT_IDS.items():
        print(f"  {key}) {user['name']}")
    
    choice = input("Enter the number of the recipient: ")
    
    if choice not in USER_CHAT_IDS:
        logger.error(f"Invalid choice '{choice}'. Exiting.")
        return
    
    selected_user = USER_CHAT_IDS[choice]
    SELECTED_CHAT_ID = selected_user["id"]
    SELECTED_USER_NAME = selected_user["name"]
    
    logger.info(f"Recipient for this session set to: {SELECTED_USER_NAME} (ID: {SELECTED_CHAT_ID})")
    
    # If on Linux, provide a helpful message about capabilities
    if sys.platform == "linux" or sys.platform == "linux2":
        logger.info("On Linux, if hotkeys are not registering, ensure your Python executable has CAP_SYS_RAWIO.")
        logger.info("You might need to run: sudo setcap 'cap_sys_rawio+ep' /home/kushal/Documents/code/screenshot_answerer/venv/bin/python")
        logger.info("If using a virtual environment, and the above path is a symlink, target the actual binary:")
        logger.info("  e.g., sudo setcap 'cap_sys_rawio+ep' /usr/bin/python3.10")
    
    # Create and start the asyncio event loop in a separate thread
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=run_async_loop, args=(loop,), daemon=True)
    loop_thread.start()
    
    logger.info("Asyncio event loop started in a separate thread.")
    
    try:
        # Initialize the Telegram bot
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        logger.info("Telegram Bot object initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Telegram Bot: {str(e)}")
        return
    
    # Register hotkeys with the keyboard library - use the original format, not formatted
    try:
        # Use the original hotkey format with plus signs
        keyboard.add_hotkey(OCR_HOTKEY, perform_ocr_task)
        keyboard.add_hotkey(SELECTION_HOTKEY, perform_selection_task)
        keyboard.add_hotkey(EXIT_HOTKEY, on_exit)
        
        logger.info("Configured hotkeys for listener:")
        # Only format for display
        logger.info(f"  - '{format_hotkey(OCR_HOTKEY)}' will trigger 'perform_ocr_task'")
        logger.info(f"  - '{format_hotkey(SELECTION_HOTKEY)}' will trigger 'perform_selection_task'")
        logger.info(f"  - Press '{EXIT_HOTKEY}' to exit the application.")
        
        # Send a welcome message via Telegram
        send_telegram_message(f"🚀 AI Assistant is ready! Connected to {SELECTED_USER_NAME}.")
        
        logger.info(f"AI Telegram Bot tool is running for {SELECTED_USER_NAME}.")
        logger.info("Listener is active and waiting for hotkey presses.")
        
        # Keep the script running until exit_event is set
        while not exit_event.is_set():
            time.sleep(0.1)
            
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        logger.exception(e)
    finally:
        # Clean up resources
        keyboard.unhook_all()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=1.0)
        logger.info("Application terminated.")

if __name__ == "__main__":
    main()
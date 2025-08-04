import sys
import threading
import pyscreenshot as ImageGrab
import keyboard
import time
import os
import json
import re  # <-- ADDED THIS IMPORT
import google.generativeai as genai
from dotenv import load_dotenv
import telegram
import asyncio
from concurrent.futures import Future
import logging
from logging.handlers import RotatingFileHandler
import tempfile
import string
import pyperclip

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

NEETCODE_PROMPT_VISION = (
    "You are an expert programmer solving a problem from the NeetCode 150 list, shown in the attached image. "
    "Analyze the image and provide a clean, efficient Python solution. "
    "Your response *MUST* strictly follow this format, with no other text or explanations:\n"
    "TYPE:CODE\n"
    "LANGUAGE:Python\n"
    "CODE:\n"
    "<code>"
)

MCQ_PROMPT_VISION = (
    "You are an expert MCQ solver. The multiple-choice question is in the attached image. "
    "Analyze the image and provide the single best answer. "
    "Your response *MUST* strictly follow this format, with no other text or explanations:\n"
    "TYPE:MCQ\n"
    "ANSWER:<Option Letter>\n"
    "EXPLANATION:<A very brief, one-sentence explanation.>"
)

USER_CHAT_IDS = {
    "1": {"name": "Jeevan", "id": "7107828513"},
    "2": {"name": "Kushal", "id": "1931229819"},
    "3": {"name": "Shahbhaaz", "id": "5963030030"},
    "4": {"name": "Somnath", "id": "7774323731"}
}
SELECTED_CHAT_ID = None
SELECTED_USER_NAME = None

MOD_KEY = "command" if sys.platform == "darwin" else "ctrl"
OCR_CODE_HOTKEY = f'{MOD_KEY}+shift+1'
OCR_MCQ_HOTKEY = f'{MOD_KEY}+shift+2'

AI_MODEL = "gemini-1.5-flash"

LOG_FILE = 'application.log'
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3
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
    if issubclass(exc_type, KeyboardInterrupt): sys.__excepthook__(exc_type, exc_value, exc_traceback)
    else: logger.critical("Unhandled exception:", exc_info=(exc_type, exc_value, exc_traceback))
sys.excepthook = handle_exception
loop = None
telegram_bot = None
loop_thread = None
def format_hotkey_for_display(hotkey_str: str) -> str: return hotkey_str.replace('+', ' ').upper()
def escape_markdown_v2(text: str) -> str:
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    text = text.replace('\\', '\\\\')
    for char in special_chars: text = text.replace(char, f'\\{char}')
    return text
async def send_telegram_message_async(message_text: str):
    if not telegram_bot or not SELECTED_CHAT_ID: return
    escaped_message = escape_markdown_v2(message_text)
    try:
        await telegram_bot.send_message(chat_id=int(SELECTED_CHAT_ID), text=escaped_message, parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
    except Exception as e: logger.exception(f"Failed to send Telegram message: {e}")
async def send_code_as_file_async(code_text: str, caption: str):
    if not telegram_bot or not SELECTED_CHAT_ID: return
    if not code_text or not code_text.strip():
        await send_telegram_message_async("The AI did not generate any code.")
        return
    escaped_caption = escape_markdown_v2(caption)
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.py', encoding='utf-8') as temp_file:
            temp_file.write(code_text)
            temp_file_path = temp_file.name
        with open(temp_file_path, 'rb') as file_to_send:
            await telegram_bot.send_document(chat_id=int(SELECTED_CHAT_ID), document=file_to_send, filename="solution.py", caption=escaped_caption, parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.exception("Error sending code as file.")
        await send_telegram_message_async(f"An internal error occurred: {e}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path): os.remove(temp_file_path)
def run_async_task(coro):
    if loop and loop.is_running(): return asyncio.run_coroutine_threadsafe(coro, loop)
    f = Future()
    f.set_exception(RuntimeError("Asyncio event loop not running"))
    return f

def get_ai_response_from_image(prompt_text: str) -> str:
    print("   -> Capturing screen...")
    screenshot = ImageGrab.grab()
    print("   -> Screenshot captured. Sending to AI...")
    
    model = genai.GenerativeModel(AI_MODEL)
    response = model.generate_content([prompt_text, screenshot])
    
    print("   -> AI response received.")
    return response.text.strip()

def handle_code_response(ai_raw_response: str):
    """
    Parses a TYPE:CODE response, cleans it with regex, copies to clipboard, 
    and sends to Telegram.
    """
    if ai_raw_response.startswith("TYPE:CODE"):
        try:
            code_text = ai_raw_response.split("CODE:", 1)[1].strip()

            # --- UPDATED: Use a regular expression to extract code ---
            # This pattern looks for a ``` block and extracts the content inside.
            # re.DOTALL makes '.' match newlines, which is crucial for multiline code.
            match = re.search(r'```(?:python|py)?\s*\n?(.*)```', code_text, re.DOTALL)
            if match:
                # If a markdown block is found, use the content inside it.
                code_text = match.group(1).strip()
            # If no markdown block is found, the original code_text is used.
            # This makes the script robust.
            # -----------------------------------------------------------

            if not code_text:
                run_async_task(send_telegram_message_async("The AI did not generate any code."))
                return
            
            pyperclip.copy(code_text)
            print("   -> Solution copied to clipboard!")
            caption = "NeetCode solution generated (and copied to your clipboard):"
            run_async_task(send_code_as_file_async(code_text, caption))
        except Exception as e:
            print(f"   -> ERROR: Failed to process AI response: {e}")
            run_async_task(send_telegram_message_async(f"AI returned a malformed code answer."))
    else:
        run_async_task(send_telegram_message_async(f"The AI did not return a valid code block."))


def handle_mcq_response(ai_raw_response: str):
    if ai_raw_response.startswith("TYPE:MCQ"):
        try:
            lines = ai_raw_response.strip().split('\n')
            answer_line = next((line for line in lines if line.startswith("ANSWER:")), None)
            explanation_line = next((line for line in lines if line.startswith("EXPLANATION:")), None)
            
            mcq_answer = answer_line.split(":", 1)[1].strip() if answer_line else "Not found"
            explanation = explanation_line.split(":", 1)[1].strip() if explanation_line else "No explanation provided."

            response_message = f"MCQ Answer: *{mcq_answer}*\n\n*Explanation:*\n{explanation}"
            run_async_task(send_telegram_message_async(response_message))
        except Exception as e:
            print(f"   -> ERROR: Failed to process AI response: {e}")
            run_async_task(send_telegram_message_async(f"AI returned a malformed MCQ answer."))
    else:
        run_async_task(send_telegram_message_async(f"The AI did not return a valid MCQ answer."))

def perform_code_hotkey_action():
    print("\n" + "-"*30)
    print("✅ Hotkey for 'Code Solver' detected!")
    try:
        ai_response = get_ai_response_from_image(NEETCODE_PROMPT_VISION)
        handle_code_response(ai_response)
        print("✅ Workflow complete!")
        print("-"*30 + "\n")
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        run_async_task(send_telegram_message_async(f"A critical error occurred: {e}"))

def perform_mcq_hotkey_action():
    print("\n" + "-"*30)
    print("✅ Hotkey for 'MCQ Solver' detected!")
    try:
        ai_response = get_ai_response_from_image(MCQ_PROMPT_VISION)
        handle_mcq_response(ai_response)
        print("✅ Workflow complete!")
        print("-"*30 + "\n")
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        run_async_task(send_telegram_message_async(f"A critical error occurred: {e}"))

def main():
    global loop, telegram_bot, loop_thread, SELECTED_CHAT_ID, SELECTED_USER_NAME
    logger.info("Starting application.")
    if sys.platform.startswith('linux') and os.geteuid() != 0:
        print("\nFATAL: Please run this script with 'sudo'. Example: sudo python3 script.py")
        return

    while True:
        print("\n--- Who is the recipient for this session? ---")
        for key, user_info in USER_CHAT_IDS.items():
            print(f"  {key}) {user_info['name']}")
        choice = input("Enter the number of the recipient: ")
        if choice in USER_CHAT_IDS:
            SELECTED_CHAT_ID, SELECTED_USER_NAME = USER_CHAT_IDS[choice]['id'], USER_CHAT_IDS[choice]['name']
            break
        else: print("Invalid choice.")
            
    if not all([TELEGRAM_BOT_TOKEN, GEMINI_API_KEY]):
        logger.critical("Missing API keys in your .env file.")
        return

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    logger.info("Asyncio event loop started.")
    time.sleep(0.1)
    
    try:
        telegram_bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        genai.configure(api_key=GEMINI_API_KEY)
        keyboard.add_hotkey(OCR_CODE_HOTKEY, perform_code_hotkey_action)
        keyboard.add_hotkey(OCR_MCQ_HOTKEY, perform_mcq_hotkey_action)
        
        print("\n" + "="*50)
        print("✅ AI Telegram Bot is running.")
        print(f"   Hotkeys are active for {SELECTED_USER_NAME}.")
        print(f"   - {format_hotkey_for_display(OCR_CODE_HOTKEY)} -> Code Solver")
        print(f"   - {format_hotkey_for_display(OCR_MCQ_HOTKEY)} -> MCQ Solver")
        print("   Press Ctrl+C in this terminal to stop.")
        print("="*50 + "\n")
        
        keyboard.wait()
    except Exception as e:
        logger.critical("An error occurred during main setup.", exc_info=True)
    finally:
        if loop and loop.is_running(): loop.call_soon_threadsafe(loop.stop)
        logger.info("Application exited.")

if __name__ == "__main__":
    main()

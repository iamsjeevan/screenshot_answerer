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
from twilio.rest import Client
from dotenv import load_dotenv
import pyperclip # NEW: Import pyperclip for clipboard operations

# --- NEW: Load the environment variables from the .env file ---
load_dotenv()

# --- SAFE CONFIGURATION ---
ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
YOUR_PHONE_NUMBER = os.environ.get("YOUR_PHONE_NUMBER")

# Non-secret configuration
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"

# Tesseract path for Windows
if sys.platform == "win32":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Hotkey configuration
MOD_KEY = "<cmd>" if sys.platform == "darwin" else "<ctrl>"
OCR_HOTKEY = f'{MOD_KEY}+<shift>+1' # Original hotkey for OCR from screenshot
SELECTION_HOTKEY = f'{MOD_KEY}+<shift>+2' # NEW: Hotkey for sending selected text (from clipboard)

AI_MODEL = "gemini-2.5-flash-preview-05-20"
# Max characters per single WhatsApp message part (Twilio's limit is 1600, 1500 is safer)
MESSAGE_CHAR_LIMIT = 1500 
# Delay between sending multiple parts of a message, to ensure order and avoid rate limits
TIME_BETWEEN_MESSAGES_SEC = 2 

def get_ai_answer(input_text: str) -> str:
    """
    Sends input text (either from OCR or clipboard) to a Gemini AI model
    and returns the generated Python code.
    """
    if not GEMINI_API_KEY:
        return "ERROR: GEMINI_API_KEY not found in .env file."
    
    # The prompt is still geared towards Python code solutions.
    # If you want a more general answer for selected text, you'd need a different prompt
    # or a way to choose between prompts.
    prompt = f"Based on the following text, provide a Python code solution. ONLY the raw Python code. No comments or explanation.\n\nText:\n---\n{input_text}\n---"
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(AI_MODEL)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error from AI: {e}"

def split_message_into_chunks(text: str, chunk_size: int) -> list[str]:
    """
    Splits a long string into fixed-size chunks for sending as multiple messages.
    """
    if not text.strip():
        return ["No content to send."]

    chunks = []
    if len(text) <= chunk_size:
        return [text]

    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
    
    return chunks

def send_plain_whatsapp_message(message_body: str):
    """
    Sends a WhatsApp message. If the message is too long, it splits it into
    multiple parts and sends them individually with a delay.
    """
    if not message_body or not message_body.strip():
        message_body = "No answer was generated."

    message_parts = split_message_into_chunks(message_body, MESSAGE_CHAR_LIMIT)
    
    client = None
    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Twilio client: {e}")
        return

    if not client:
        return

    total_parts = len(message_parts)
    for i, part in enumerate(message_parts):
        try:
            prefix = f"Part {i+1}/{total_parts}:\n"
            final_part_body = prefix + part

            # Safeguard against prefix making the part too long
            if len(final_part_body) > MESSAGE_CHAR_LIMIT: 
                 # Adjust the part content to fit after adding prefix
                 final_part_body = prefix + part[:MESSAGE_CHAR_LIMIT - len(prefix) - 3] + "..." 

            message = client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                body=final_part_body,
                to=YOUR_PHONE_NUMBER
            )
            print(f"[TWILIO] Message part {i+1}/{total_parts} sent successfully! SID: {message.sid}")
            
            if i < total_parts - 1:
                time.sleep(TIME_BETWEEN_MESSAGES_SEC)
                
        except Exception as e:
            print(f"[ERROR] Failed to send Twilio message part {i+1}/{total_parts}: {e}")

def perform_ocr_task():
    """
    Captures a screenshot, performs OCR, gets an AI answer, and sends it via WhatsApp.
    This is the original functionality.
    """
    print("[INFO] Performing OCR task (from screenshot)...")
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[0] 
            sct_img = sct.grab(monitor) 
        
        pil_image = Image.frombytes("RGB", sct_img.size, sct_img.rgb) 
        ocr_text = pytesseract.image_to_string(pil_image)
        
        if not ocr_text.strip():
            print("[INFO] No text recognized by OCR.")
            send_plain_whatsapp_message("No text recognized from screenshot.")
            return
        
        ai_answer = get_ai_answer(ocr_text)
        send_plain_whatsapp_message(ai_answer)
    except Exception as e:
        print(f"[ERROR] An error occurred in perform_ocr_task: {e}")
        send_plain_whatsapp_message(f"An internal error occurred during OCR task: {e}")

def perform_selection_task():
    """
    Reads text from the clipboard, gets an AI answer, and sends it via WhatsApp.
    This is the NEW functionality.
    """
    print("[INFO] Performing selection task (from clipboard)...")
    try:
        selected_text = pyperclip.paste() # Get text from clipboard
        
        if not selected_text.strip():
            print("[INFO] Clipboard is empty or contains no readable text.")
            send_plain_whatsapp_message("Clipboard is empty. Please copy text first.")
            return
        
        ai_answer = get_ai_answer(selected_text)
        send_plain_whatsapp_message(ai_answer)
    except pyperclip.PyperclipException as e:
        print(f"[ERROR] Failed to access clipboard: {e}. Please ensure you have xclip/xsel installed on Linux or a GUI clipboard is available.")
        send_plain_whatsapp_message(f"Could not access clipboard: {e}")
    except Exception as e:
        print(f"[ERROR] An error occurred in perform_selection_task: {e}")
        send_plain_whatsapp_message(f"An internal error occurred during selection task: {e}")

def main():
    """
    Main function to initialize the script and hotkey listener.
    """
    if not all([ACCOUNT_SID, AUTH_TOKEN, GEMINI_API_KEY, YOUR_PHONE_NUMBER]):
        print("[FATAL ERROR] One or more variables are missing from your .env file.")
        print("Please ensure TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, GEMINI_API_KEY, and YOUR_PHONE_NUMBER are set.")
        return

    # Map hotkeys to their respective functions
    hotkeys_to_listen = {
        OCR_HOTKEY: perform_ocr_task,
        SELECTION_HOTKEY: perform_selection_task # NEW: Add the clipboard hotkey
    }

    with keyboard.GlobalHotKeys(hotkeys_to_listen) as listener:
        print("[INFO] AI WhatsApp API tool is running securely (using .env).")
        print(f"[SUCCESS] Listener is active.")
        print(f"  - Press {' '.join(OCR_HOTKEY.replace('<','').replace('>','').split('+'))} for OCR from screenshot.")
        print(f"  - Press {' '.join(SELECTION_HOTKEY.replace('<','').replace('>','').split('+'))} to send selected text (from clipboard).")
        listener.join()

if __name__ == "__main__":
    main()
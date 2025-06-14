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
# --- NEW: Import the dotenv library ---
from dotenv import load_dotenv

# --- NEW: Load the environment variables from the .env file ---
# This is the line that makes everything work automatically.
load_dotenv()

# --- SAFE CONFIGURATION ---
# The script will now read these values from the .env file we just created.
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
OCR_HOTKEY = f'{MOD_KEY}+<shift>+1'
AI_MODEL = "gemini-2.5-flash-preview-05-20"
MESSAGE_CHAR_LIMIT = 1500

def get_ai_answer(ocr_text: str) -> str:
    if not GEMINI_API_KEY:
        return "ERROR: GEMINI_API_KEY not found in .env file."
    prompt = f"Based on the following text, provide a Python code solution. ONLY the raw Python code. No comments or explanation.\n\nText:\n---\n{ocr_text}\n---"
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(AI_MODEL)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error from AI: {e}"

def send_plain_whatsapp_message(message_body: str):
    if not message_body or not message_body.strip():
        message_body = "No answer was generated."
    
    if len(message_body) > MESSAGE_CHAR_LIMIT:
        message_body = message_body[:MESSAGE_CHAR_LIMIT] + "..."
    
    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        message = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=message_body,
            to=YOUR_PHONE_NUMBER
        )
        print(f"[TWILIO] Message sent successfully! SID: {message.sid}")
    except Exception as e:
        print(f"[ERROR] Failed to send Twilio message: {e}")

def perform_task():
    try:
        with mss.mss() as sct:
            img = sct.grab(sct.monitors[0])
        ocr_text = pytesseract.image_to_string(Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX"))
        if not ocr_text.strip(): return
        ai_answer = get_ai_answer(ocr_text)
        send_plain_whatsapp_message(ai_answer)
    except Exception as e:
        print(f"[ERROR] An error occurred in perform_task: {e}")

def main():
    if not all([ACCOUNT_SID, AUTH_TOKEN, GEMINI_API_KEY, YOUR_PHONE_NUMBER]):
        print("[FATAL ERROR] One or more variables are missing from your .env file.")
        return

    hotkeys_to_listen = {OCR_HOTKEY: perform_task}
    with keyboard.GlobalHotKeys(hotkeys_to_listen) as listener:
        print("[INFO] AI WhatsApp API tool is running securely (using .env).")
        print(f"[SUCCESS] Listener is active. Press {' '.join(OCR_HOTKEY.replace('<','').replace('>','').split('+'))} to trigger.")
        listener.join()

if __name__ == "__main__":
    main()
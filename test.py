import os
import sys
import asyncio
import tempfile
import pyscreenshot as ImageGrab
import telegram
from dotenv import load_dotenv
from pynput import keyboard
import threading

# --- Configuration ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# It's good practice to ensure the Chat ID is a string, though it often works as an integer.
JEEVAN_CHAT_ID = "7107828513"

# --- Hotkey Definition ---
HOTKEY_COMBINATION = {
    keyboard.KeyCode.from_char('a'),
    keyboard.KeyCode.from_char('b'),
    keyboard.KeyCode.from_char('c')
}
current_keys = set()

# --- The Lock ---
# This prevents the hotkey from firing multiple times if keys are held down.
hotkey_active = False

# --- Main Logic ---

async def send_screenshot_to_telegram(image_path: str):
    """Asynchronously sends the screenshot to Telegram."""
    # Each async task should have its own bot instance in this threaded context
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    print("   -> Sending screenshot...")
    try:
        with open(image_path, 'rb') as photo_file:
            await bot.send_photo(
                chat_id=JEEVAN_CHAT_ID,
                photo=photo_file,
                caption="Here is the screenshot you requested."
            )
        print("   ✅ Screenshot sent successfully!")
    except Exception as e:
        print(f"   ❌ Failed to send screenshot: {e}")
    finally:
        # Clean up the temp file after sending
        if os.path.exists(image_path):
            os.remove(image_path)

def capture_and_send_screenshot():
    """
    This function now runs in a separate thread.
    It captures, saves, and then asynchronously sends the screenshot.
    """
    print("\n✅ Hotkey 'A+B+C' detected!")
    print("   -> Capturing screen...")
    temp_file_path = None
    try:
        # Create a temporary file to save the screenshot
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
            temp_file_path = temp_file.name

        # 1. Capture the screen
        screenshot = ImageGrab.grab()
        # 2. Save the screenshot to the temp file
        screenshot.save(temp_file_path)
        print(f"   -> Screenshot saved to {temp_file_path}")

        # 3. Run the async sending function in a new event loop for this thread
        asyncio.run(send_screenshot_to_telegram(temp_file_path))

    except Exception as e:
        print(f"   ❌ An error occurred during the process: {e}")
        # Ensure cleanup even if the async part fails
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

# --- pynput Listener Functions (CORRECTED LOGIC) ---

def on_press(key):
    global hotkey_active
    if key in HOTKEY_COMBINATION:
        current_keys.add(key)
        if all(k in current_keys for k in HOTKEY_COMBINATION) and not hotkey_active:
            hotkey_active = True
            # --- THE KEY CHANGE IS HERE ---
            # Run the slow function in a separate thread to not block the listener
            worker_thread = threading.Thread(target=capture_and_send_screenshot, daemon=True)
            worker_thread.start()

def on_release(key):
    global hotkey_active
    try:
        current_keys.remove(key)
        if key in HOTKEY_COMBINATION:
            # Reset the lock as soon as one of the keys is released
            hotkey_active = False
    except KeyError:
        pass

def main():
    """Sets up the environment and starts the listener."""
    if not TELEGRAM_BOT_TOKEN:
        print("FATAL: TELEGRAM_BOT_TOKEN not found in your .env file.")
        sys.exit(1)

    print("="*50)
    print("✅ Screenshot Listener is running (Parallel Version).")
    print("   Press 'A+B+C' (at the same time) to send a screenshot.")
    print("   The script will remain responsive even while uploading.")
    print("   Press 'Ctrl+C' in this terminal to stop the script.")
    print("="*50)

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            print("\nScript stopped by user. Exiting.")
            listener.stop()

if __name__ == "__main__":
    main()
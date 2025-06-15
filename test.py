import os
from dotenv import load_dotenv
import telegram
from datetime import datetime
import sys
import asyncio

# Load environment variables from .env file
load_dotenv()

# Get Telegram Bot Token and Chat ID from environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- DEBUG LOGS START ---
print(f"DEBUG: Attempting to load .env variables...")
print(f"DEBUG: Loaded TELEGRAM_BOT_TOKEN (first 5 and last 5 chars): {TELEGRAM_BOT_TOKEN[:5]}...{TELEGRAM_BOT_TOKEN[-5:] if TELEGRAM_BOT_TOKEN else 'None'}")
print(f"DEBUG: Loaded TELEGRAM_CHAT_ID: '{TELEGRAM_CHAT_ID}'")
print(f"DEBUG: Path to .env file being considered: {os.path.abspath('.env')}")
print(f"DEBUG: Current Working Directory: {os.getcwd()}")
# --- DEBUG LOGS END ---


async def test_telegram_bot_message():
    """
    Sends a test message to Telegram using the configured bot token and chat ID.
    """
    print("\n[INFO] Starting Telegram bot test message sending process...")

    if not TELEGRAM_BOT_TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN not found in your .env file.")
        print("Please ensure your .env file has: TELEGRAM_BOT_TOKEN=\"YOUR_BOT_TOKEN\"")
        return

    if not TELEGRAM_CHAT_ID:
        print("[ERROR] TELEGRAM_CHAT_ID not found in your .env file.")
        print("Please ensure your .env file has: TELEGRAM_CHAT_ID=\"YOUR_CHAT_ID\"")
        print("Remember to send a message to your bot on Telegram first to get your chat ID!")
        return

    try:
        chat_id_int = int(TELEGRAM_CHAT_ID)
        print(f"[INFO] Converted TELEGRAM_CHAT_ID to integer: {chat_id_int}")
    except ValueError:
        print(f"[ERROR] Invalid TELEGRAM_CHAT_ID: '{TELEGRAM_CHAT_ID}'. It must be a number (e.g., '123456789' or '-1234567890').")
        return

    bot = None
    try:
        print("[INFO] Initializing Telegram Bot with provided token...")
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        print("[INFO] Telegram Bot initialized successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to initialize Telegram Bot: {e}")
        print("Please check if your TELEGRAM_BOT_TOKEN is correct and has no typos.")
        return

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # FIX: Escaped the '!' character and other potential special characters for MarkdownV2
    # The list of characters to escape for MARKDOWN_V2 is:
    # _, *, [, ], (, ), ~, `, >, #, +, -, =, |, {, }, ., !
    # We are using a simple escape function for common text to avoid future issues.
    def escape_markdown_v2(text):
        special_chars = '_*[]()~`>#+-=|{}.!'
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    # Apply escaping to the dynamic parts or the whole message if not inside a code block
    escaped_current_time = escape_markdown_v2(current_time)

    test_message = (
        f"Hello from your Python Telegram Test Bot\\!\n\n" # Escaped '!'
        f"This message was sent at: `{escaped_current_time}`\n"
        f"If you see this, your bot setup is working\\!\n" # Escaped '!'
        f"Python Version: {escape_markdown_v2(sys.version.split(' ')[0])}" # Escaped for safety
    )
    
    try:
        print(f"[INFO] Attempting to send message to Chat ID: {chat_id_int}")
        await bot.send_message(
            chat_id=chat_id_int,
            text=test_message,
            parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
        )
        print("[SUCCESS] Test message sent to Telegram!")
        print(f"Check your Telegram chat with your bot (ID: {TELEAGRAM_CHAT_ID}).")
    except telegram.error.TelegramError as e:
        print(f"[ERROR] Failed to send message to Telegram: {e}")
        if "Forbidden: bot was blocked by the user" in str(e):
            print("  -> Troubleshooting Tip: The bot might be blocked by you. Unblock it in Telegram.")
        elif "Bad Request: chat not found" in str(e) or "Bad Request: user not found" in str(e):
            print("  -> Troubleshooting Tip: The TELEGRAM_CHAT_ID might be incorrect or you haven't started a chat with the bot yet.")
            print("     Remember to send your bot *any* message first, then get your chat ID again from:")
            print(f"     https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates")
        elif "Unauthorized" in str(e):
            print("  -> Troubleshooting Tip: The TELEGRAM_BOT_TOKEN might be incorrect or revoked. Get a new one from @BotFather.")
        elif "Timed out" in str(e):
            print("  -> Troubleshooting Tip: Network issue or Telegram API is slow. Check your internet connection.")
        elif "Can't parse entities" in str(e):
            print(f"  -> Troubleshooting Tip: Markdown parsing error. A character needs to be escaped. Error details: {e}")
            print("     Common characters requiring escape: _ * [ ] ( ) ~ ` > # + - = | { } . !")
        else:
            print("  -> Other Telegram API error. Review the error message above for details.")
    except Exception as e:
        print(f"[FATAL ERROR] An unexpected system error occurred during message sending: {e}")

if __name__ == "__main__":
    asyncio.run(test_telegram_bot_message())
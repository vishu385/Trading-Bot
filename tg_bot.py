import telebot
from telebot.types import BotCommand
import os
import json
import subprocess
import threading
import sys
import shutil

BOT_TOKEN = "8981260576:AAEGmRqNdFn1K50Uqrvxe2UZ2-Yf-1o1WlI"

bot = telebot.TeleBot(BOT_TOKEN)
bot.set_my_commands([
    BotCommand("start_bomber", "Start the bomber process"),
    BotCommand("stop_bomber", "Stop the bomber process"),
    BotCommand("addnumbers", "Add target numbers in bulk"),
    BotCommand("addproxies", "Add Webshare proxies in bulk"),
    BotCommand("clearnumbers", "Clear your numbers list"),
    BotCommand("clearproxies", "Clear your proxies list"),
    BotCommand("setloop", "Set Global Loop count"),
    BotCommand("setthread", "Set Thread count"),
    BotCommand("setresend", "Set SMS Resend count"),
    BotCommand("menu", "Show the main menu")
])

user_processes = {}
USER_DIR_BASE = "users"

if not os.path.exists(USER_DIR_BASE):
    os.makedirs(USER_DIR_BASE)

def get_user_dir(chat_id):
    path = os.path.join(USER_DIR_BASE, str(chat_id))
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def update_config(chat_id, key, value):
    user_dir = get_user_dir(chat_id)
    config_file = os.path.join(user_dir, "config.json")
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            data = json.load(f)
    else:
        # Default starting config for new users
        data = {"resend_count": 2, "loop_count": 1, "threads": 2}
    
    data[key] = value
    with open(config_file, "w") as f:
        json.dump(data, f, indent=4)

@bot.message_handler(commands=['start_bomber'])
def start_bomber(message):
    chat_id = message.chat.id
    if chat_id in user_processes and user_processes[chat_id].poll() is None:
        bot.reply_to(message, "⚠️ Your bomber is already running!")
        return
    
    user_dir = get_user_dir(chat_id)
    num_file = os.path.join(user_dir, "numbers.txt")
    
    if not os.path.exists(num_file) or os.path.getsize(num_file) == 0:
        bot.reply_to(message, "⚠️ You haven't added any numbers! Please use /addnumbers first.")
        return
        
    bot.reply_to(message, "🚀 Starting your isolated Paysafe Bomber...")
    
    # Path to the main script which resides in the same directory as tg_bot.py
    script_path = os.path.abspath("paysafe_bomber.py")
    
    # We run the script with cwd=user_dir, so it reads its numbers.txt, config.json etc from the user's isolated folder!
    process = subprocess.Popen(
        [sys.executable, "-u", script_path], 
        cwd=user_dir,
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True,
        encoding='utf-8',
        bufsize=1
    )
    
    user_processes[chat_id] = process
    threading.Thread(target=monitor_bomber, args=(chat_id, process), daemon=True).start()

@bot.message_handler(commands=['stop_bomber'])
def stop_bomber(message):
    chat_id = message.chat.id
    if chat_id in user_processes and user_processes[chat_id].poll() is None:
        user_processes[chat_id].terminate()
        user_processes[chat_id] = None
        bot.reply_to(message, "🛑 Your bomber has been stopped.")
    else:
        bot.reply_to(message, "⚠️ You don't have any bomber currently running.")

@bot.message_handler(commands=['setloop', 'setthread', 'setresend'])
def handle_config_commands(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, f"Usage: {parts[0]} <number>")
        return
    
    try:
        val = int(parts[1])
        if parts[0] == '/setloop':
            update_config(message.chat.id, 'loop_count', val)
            bot.reply_to(message, f"✅ Loop count set to {val} for your account.")
        elif parts[0] == '/setthread':
            update_config(message.chat.id, 'threads', val)
            bot.reply_to(message, f"✅ Threads set to {val} for your account.")
        elif parts[0] == '/setresend':
            update_config(message.chat.id, 'resend_count', val)
            bot.reply_to(message, f"✅ Resends set to {val} for your account.")
    except ValueError:
        bot.reply_to(message, "⚠️ Please provide a valid number.")

@bot.message_handler(commands=['addnumbers'])
def handle_add_numbers(message):
    msg = bot.reply_to(message, "Send me the list of numbers in bulk (one per line):")
    bot.register_next_step_handler(msg, process_add_numbers)

def process_add_numbers(message):
    if message.text.strip().startswith('/'):
        bot.reply_to(message, "❌ Operation cancelled because you entered a command instead of numbers. Please use /addnumbers again.")
        return
        
    user_dir = get_user_dir(message.chat.id)
    numbers = message.text.strip().split('\n')
    valid_numbers = [n.strip() for n in numbers if n.strip()]
    
    # Append or overwrite? Standard behavior for this is overwrite. 
    # User requested separate clear command so they can clear, meaning this could just overwrite. 
    with open(os.path.join(user_dir, "numbers.txt"), "w") as f:
        f.write("\n".join(valid_numbers))
        
    bot.reply_to(message, f"✅ Successfully saved {len(valid_numbers)} numbers!")

@bot.message_handler(commands=['addproxies'])
def handle_add_proxies(message):
    msg = bot.reply_to(message, "Send me the list of proxies in IP:PORT:USER:PASS format (one per line):")
    bot.register_next_step_handler(msg, process_add_proxies)

def process_add_proxies(message):
    if message.text.strip().startswith('/'):
        bot.reply_to(message, "❌ Operation cancelled because you entered a command instead of proxies. Please use /addproxies again.")
        return
        
    user_dir = get_user_dir(message.chat.id)
    proxies = message.text.strip().split('\n')
    valid_proxies = [p.strip() for p in proxies if p.strip()]
    
    with open(os.path.join(user_dir, "proxies.txt"), "w") as f:
        f.write("\n".join(valid_proxies))
        
    bot.reply_to(message, f"✅ Successfully saved {len(valid_proxies)} proxies!")

@bot.message_handler(commands=['clearnumbers'])
def clear_numbers(message):
    user_dir = get_user_dir(message.chat.id)
    with open(os.path.join(user_dir, "numbers.txt"), "w") as f:
        f.write("")
    bot.reply_to(message, "🧹 Your numbers list has been completely cleared!")

@bot.message_handler(commands=['clearproxies'])
def clear_proxies(message):
    user_dir = get_user_dir(message.chat.id)
    with open(os.path.join(user_dir, "proxies.txt"), "w") as f:
        f.write("")
    bot.reply_to(message, "🧹 Your proxies list has been completely cleared!")

@bot.message_handler(commands=['menu', 'start'])
def show_menu(message):
    menu_text = (
        "🤖 **Paysafe Bomber Controller (Multi-User)** 🤖\n\n"
        "/start_bomber - Start your bomber process\n"
        "/stop_bomber - Stop your bomber process\n"
        "/addnumbers - Add target numbers in bulk\n"
        "/clearnumbers - Clear your numbers list\n"
        "/addproxies - Add Webshare proxies in bulk\n"
        "/clearproxies - Clear your proxies list\n"
        "/setloop <num> - Set Global Loop count\n"
        "/setthread <num> - Set Thread count\n"
        "/setresend <num> - Set SMS Resend count\n"
    )
    bot.reply_to(message, menu_text, parse_mode="Markdown")

def monitor_bomber(chat_id, process):
    while process and process.poll() is None:
        line = process.stdout.readline()
        if not line:
            continue
        line = line.strip()
        if not line:
            continue
            
        if "[+] Temp Email:" in line:
            bot.send_message(chat_id, f"📧 {line}")
            
        elif "[+] Email Verified Successfully" in line:
            bot.send_message(chat_id, f"✅ {line}")
            
        elif "[+] Personal Details Accepted!" in line or "[+] Address Data Accepted!" in line:
            bot.send_message(chat_id, f"📝 {line}")
            
        elif "FIRED SUCCESSFULLY" in line:
            bot.send_message(chat_id, f"🚀 {line}")
            
        elif "API Proof" in line or "HTTP 200" in line:
            bot.send_message(chat_id, f"ℹ️ {line}")
            
        elif "Waiting" in line and "before Resend" in line:
            bot.send_message(chat_id, f"⏳ {line}")
            
        elif "[-] Failed" in line or "[-] Thread crashed:" in line or "[-] API Verification failed" in line:
            bot.send_message(chat_id, f"❌ {line}")

    bot.send_message(chat_id, "🛑 Your bomber process has finished all loops or was stopped.")
    if chat_id in user_processes and user_processes[chat_id] == process:
        user_processes[chat_id] = None

while True:
    try:
        print("Bot is polling...")
        bot.infinity_polling(timeout=20, long_polling_timeout=20)
    except Exception as e:
        print(f"Network error: {e}. Retrying in 5 seconds...")
        time.sleep(5)

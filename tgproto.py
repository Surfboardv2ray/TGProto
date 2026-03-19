import requests
import threading
import json
import os 
import time
import random
import re
import base64
import argparse

from bs4 import BeautifulSoup
from datetime import datetime, timedelta

requests.post = lambda url, **kwargs: requests.request(
    method="POST", url=url, verify=False, **kwargs
)
requests.get = lambda url, **kwargs: requests.request(
    method="GET", url=url, verify=False, **kwargs
)

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

os.system('cls' if os.name == 'nt' else 'clear')

if not os.path.exists('proxies.txt'):
    with open('proxies.txt', 'w'): pass

def json_load(path):
    with open(path, 'r', encoding="utf-8") as file:
        list_content = json.load(file)
    return list_content

def substring_del(string_list):
    string_list.sort(key=lambda s: len(s), reverse=True)
    out = []
    for s in string_list:
        if not any([s in o for o in out]):
            out.append(s)
    return out

tg_name_json = json_load('ch.json')
inv_tg_name_json = json_load('ch-inv.json')

inv_tg_name_json[:] = [x for x in inv_tg_name_json if len(x) >= 5]
inv_tg_name_json = list(set(inv_tg_name_json)-set(tg_name_json))

thrd_pars = int(os.getenv('THRD_PARS', '128'))
pars_dp = int(os.getenv('PARS_DP', '1'))

print(f'\nTotal channel names in ch.json         - {len(tg_name_json)}')
print(f'Total channel names in ch-inv.json - {len(inv_tg_name_json)}')

use_inv_tc = os.getenv('USE_INV_TC', 'n')
use_inv_tc = True if use_inv_tc.lower() == 'y' else False

start_time = datetime.now()

sem_pars = threading.Semaphore(thrd_pars)

config_all = list()
tg_name = list()
new_tg_name_json = list()

print(f'Try get new tg channels name from proxy configs in proxies.txt...')

with open("proxies.txt", "r", encoding="utf-8") as config_all_file:
    config_all = config_all_file.readlines()

pattern_telegram_user = r'(?:@)(\w{5,})|(?:%40)(\w{5,})|(?:t\.me\/)(\w{5,})'
pattern_datbef = re.compile(r'(?:data-before=")(\d*)')

for config in config_all:
    matches_usersname = re.findall(pattern_telegram_user, config, re.IGNORECASE)
    for element in matches_usersname:
        for part in element:
            if part:
                tg_name.append(part.lower())

tg_name[:] = [x for x in tg_name if len(x) >= 5]
tg_name_json[:] = [x for x in tg_name_json if len(x) >= 5]    
tg_name = list(set(tg_name))

print(f'\nFound tg channel names - {len(tg_name)}')
print(f'Total old names        - {len(tg_name_json)}')

tg_name_json.extend(tg_name)
tg_name_json = sorted(list(set(tg_name_json)))

print(f'In the end, new names  - {len(tg_name_json)}')

with open('ch.json', 'w', encoding="utf-8") as telegram_channels_file:
    json.dump(tg_name_json, telegram_channels_file, indent=4)

print(f'\nSearch for new names is over - {str(datetime.now() - start_time).split(".")[0]}')
print(f'\nStart Parsing...\n')


# regex to extract Telegram proxies
proxy_pattern = re.compile(
    r'(https://t\.me/(?:proxy|socks)\?server=[^\s"<]+|tg://(?:proxy|socks)\?server=[^\s"<]+)'
)

def process(i_url):
    sem_pars.acquire()
    html_pages = list()
    cur_url = i_url
    god_tg_name = False

    for itter in range(1, pars_dp+1):
        while True:
            try:
                response = requests.get(f'https://t.me/s/{cur_url}')
            except:
                time.sleep(random.randint(5,25))
            else:
                if itter == pars_dp:
                    print(f'{tg_name_json.index(i_url)+1} of {walen} - {i_url}')
                html_pages.append(response.text)
                last_datbef = re.findall(pattern_datbef, response.text)
                break

        if not last_datbef:
            break
        cur_url = f'{i_url}?before={last_datbef[0]}'

    for page in html_pages:
        matches = re.findall(proxy_pattern, page)
        for m in matches:
            codes.append(m.strip())
            new_tg_name_json.append(i_url)
            god_tg_name = True

    if not god_tg_name:
        inv_tg_name_json.append(i_url)

    sem_pars.release()


codes = list()

walen = len(tg_name_json)
for url in tg_name_json:
    threading.Thread(target=process, args=(url,)).start()

while threading.active_count() > 1:
    time.sleep(1)

print(f'\nParsing completed - {str(datetime.now() - start_time).split(".")[0]}')

print(f'\nCleaning and removing duplicates...')

import ipaddress

# ✅ UPDATED VALIDATION
def is_valid_proxy(url):
    try:
        server_match = re.search(r'server=([^&]+)', url)
        port_match = re.search(r'port=(\d+)', url)

        if not server_match or not port_match:
            return False

        server = server_match.group(1).strip()
        port = int(port_match.group(1))

        # ❌ exclude localhost
        if server in ["127.0.0.1", "localhost"]:
            return False

        # ✅ validate port
        if not (1 <= port <= 65535):
            return False

        # ✅ try IP validation
        try:
            ipaddress.ip_address(server)
            return True
        except:
            pass

        # ✅ allow domains (basic validation)
        if re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', server):
            return True

        return False

    except:
        return False


# cleaning
processed_codes = list(set(codes))

cleaned = []
for x in processed_codes:
    x = requests.utils.unquote(x).strip()
    x = x.replace("amp;", "")

    # convert tg:// → https://t.me/
    x = x.replace("tg://proxy", "https://t.me/proxy")
    x = x.replace("tg://socks", "https://t.me/socks")

    if is_valid_proxy(x):
        cleaned.append(x)

processed_codes = sorted(list(set(cleaned)))

print(f'\nDelete tg channels that not contains proxy configs...')

new_tg_name_json = sorted(list(set(new_tg_name_json)))
print(f'\nRemaining tg channels after deletion - {len(new_tg_name_json)}')

inv_tg_name_json = sorted(list(set(inv_tg_name_json)))

print(f'\nSave new ch.json, ch-inv.json and proxies.txt...')

with open('ch.json', 'w', encoding="utf-8") as f:
    json.dump(new_tg_name_json, f, indent=4)

with open('ch-inv.json', 'w', encoding="utf-8") as f:
    json.dump(inv_tg_name_json, f, indent=4)

with open("proxies.txt", "w", encoding="utf-8") as file:
    for code in processed_codes:
        file.write(code + "\n")

print(f'\nTime spent - {str(datetime.now() - start_time).split(".")[0]}')

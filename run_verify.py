import subprocess
import time
import json
import urllib.request
import base64
import os
import tempfile
import shutil
import socket
from websockets.sync.client import connect

def get_free_port():
    s = socket.socket()
    s.bind(('', 0))
    p = s.getsockname()[1]
    s.close()
    return p

chrome = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
port = get_free_port()
tmp_dir = tempfile.mkdtemp(prefix="chrome_test_")

cmd = [
    chrome,
    '--headless=new',
    '--disable-gpu',
    f'--user-data-dir={tmp_dir}',
    f'--remote-debugging-port={port}',
    '--no-first-run',
    '--no-default-browser-check',
    '--remote-allow-origins=*',
    '--window-size=1280,850',
    'http://localhost:8085'
]

print(f"Launching Chrome on port {port} with tmp_dir {tmp_dir}...")
proc = subprocess.Popen(cmd)

try:
    ws_url = None
    for attempt in range(20):
        try:
            time.sleep(0.5)
            with urllib.request.urlopen(f'http://localhost:{port}/json', timeout=2) as resp:
                tabs = json.loads(resp.read().decode('utf-8'))
                if tabs and 'webSocketDebuggerUrl' in tabs[0]:
                    ws_url = tabs[0]['webSocketDebuggerUrl']
                    break
        except Exception as e:
            continue

    if not ws_url:
        raise RuntimeError("Failed to connect to Chrome debugging port")

    print(f"Connected to Chrome CDP at: {ws_url}")
    with connect(ws_url) as ws:
        call_id = [1]
        def send_cmd(method, params=None):
            call_id[0] += 1
            curr_id = call_id[0]
            ws.send(json.dumps({'id': curr_id, 'method': method, 'params': params or {}}))
            while True:
                raw = ws.recv()
                res = json.loads(raw)
                if res.get('id') == curr_id:
                    return res.get('result', {})

        send_cmd('Runtime.enable')

        # 1. Capture Tab 1 (Forge Form)
        time.sleep(1)
        res = send_cmd('Page.captureScreenshot', {'format': 'png'})
        with open(r'C:\Users\USER\Downloads\webtgp\webapp\tab1_form_verified.png', 'wb') as f:
            f.write(base64.b64decode(res['data']))
        print("Captured tab1_form_verified.png")

        # 2. Click Tab 2 (Bible & Prompts)
        send_cmd('Runtime.evaluate', {
            'expression': 'document.querySelector(\'.tab-btn[data-tab="tab-prompts"]\').click();'
        })
        time.sleep(0.6)
        res = send_cmd('Page.captureScreenshot', {'format': 'png'})
        with open(r'C:\Users\USER\Downloads\webtgp\webapp\tab2_prompts_verified.png', 'wb') as f:
            f.write(base64.b64decode(res['data']))
        print("Captured tab2_prompts_verified.png")

        # 3. Click Tab 3 (9-Panel Sheet)
        send_cmd('Runtime.evaluate', {
            'expression': 'document.querySelector(\'.tab-btn[data-tab="tab-sheetmatrix"]\').click();'
        })
        time.sleep(0.6)
        res = send_cmd('Page.captureScreenshot', {'format': 'png'})
        with open(r'C:\Users\USER\Downloads\webtgp\webapp\tab3_sheet_verified.png', 'wb') as f:
            f.write(base64.b64decode(res['data']))
        print("Captured tab3_sheet_verified.png")

        # 4. Return to Tab 1 and Click Forge Character
        send_cmd('Runtime.evaluate', {
            'expression': 'document.querySelector(\'.tab-btn[data-tab="tab-forge"]\').click();'
        })
        time.sleep(0.5)

        print("Triggering Forge Character button...")
        send_cmd('Runtime.evaluate', {
            'expression': 'document.getElementById("btnForgeCharacter").click();'
        })

        print("Waiting for Forge Character API to populate...")
        for i in range(25):
            time.sleep(1)
            eval_res = send_cmd('Runtime.evaluate', {
                'expression': 'document.getElementById("masterPromptBox") ? document.getElementById("masterPromptBox").value : ""'
            })
            val = eval_res.get('result', {}).get('value', '')
            if val and len(val) > 20:
                print(f"Master Prompt successfully populated! Length: {len(val)}")
                break

        time.sleep(1)
        res = send_cmd('Page.captureScreenshot', {'format': 'png'})
        with open(r'C:\Users\USER\Downloads\webtgp\webapp\tab2_forged_results_verified.png', 'wb') as f:
            f.write(base64.b64decode(res['data']))
        print("Captured tab2_forged_results_verified.png")

        print("Verification complete!")
finally:
    proc.terminate()
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except:
        pass

import subprocess
import time
import json
import urllib.request
import base64
from websockets.sync.client import connect

chrome = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
port = 9229
cmd = [
    chrome,
    '--headless=new',
    '--disable-gpu',
    f'--user-data-dir=C:\\Users\\USER\\Downloads\\webtgp\\chrome_tmp_profile',
    f'--remote-debugging-port={port}',
    '--remote-allow-origins=*',
    '--window-size=1280,920',
    'http://localhost:8085'
]

proc = subprocess.Popen(cmd)
time.sleep(2.5)

try:
    tabs = json.loads(urllib.request.urlopen(f'http://localhost:{port}/json').read())
    ws_url = tabs[0]['webSocketDebuggerUrl']
    print('Connected to CDP at:', ws_url)
    with connect(ws_url) as ws:
        call_id = [1]
        def send_cmd(method, params=None):
            call_id[0] += 1
            curr_id = call_id[0]
            ws.send(json.dumps({'id': curr_id, 'method': method, 'params': params or {}}))
            while True:
                res = json.loads(ws.recv())
                if res.get('id') == curr_id:
                    return res.get('result', {})

        send_cmd('Runtime.enable')

        # 1. Capture Form View
        res = send_cmd('Page.captureScreenshot', {'format': 'png'})
        with open(r'C:\Users\USER\Downloads\webtgp\webapp\snap_forge_form.png', 'wb') as f:
            f.write(base64.b64decode(res['data']))
        print('Captured snap_forge_form.png')

        # 2. Click Forge Character
        print('Clicking Forge Character...')
        send_cmd('Runtime.evaluate', {
            'expression': 'document.getElementById("btnForgeCharacter").click();'
        })

        # Wait for API generation
        print('Waiting for character forging to complete...')
        for _ in range(30):
            time.sleep(1)
            val = send_cmd('Runtime.evaluate', {
                'expression': 'document.getElementById("masterPromptBox") ? document.getElementById("masterPromptBox").value : ""'
            })
            text_val = val.get('result', {}).get('value', '')
            if text_val and len(text_val) > 20:
                print('Character forged! Length:', len(text_val))
                break

        time.sleep(1)
        # 3. Capture Results
        res = send_cmd('Page.captureScreenshot', {'format': 'png'})
        with open(r'C:\Users\USER\Downloads\webtgp\webapp\snap_forge_results.png', 'wb') as f:
            f.write(base64.b64decode(res['data']))
        print('Captured snap_forge_results.png')

        print('Test script completed successfully!')
finally:
    proc.terminate()

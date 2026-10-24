import subprocess
import time
import json
import urllib.request
import base64
import os
import shutil
from websockets.sync.client import connect

chrome = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
port = 9226
tmp_profile = r'C:\Users\USER\Downloads\webtgp\chrome_tmp_profile'
os.makedirs(tmp_profile, exist_ok=True)

cmd = [
    chrome,
    '--headless=new',
    '--disable-gpu',
    f'--user-data-dir={tmp_profile}',
    f'--remote-debugging-port={port}',
    '--window-size=1280,850',
    'http://localhost:8085'
]

proc = subprocess.Popen(cmd)
time.sleep(2.5)

try:
    tabs = json.loads(urllib.request.urlopen(f'http://localhost:{port}/json').read())
    ws_url = tabs[0]['webSocketDebuggerUrl']
    print('Connected to Chrome CDP at:', ws_url)
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

        # 1. Capture Initial View (Realistic Female Face)
        res = send_cmd('Page.captureScreenshot', {'format': 'png'})
        with open(r'C:\Users\USER\Downloads\webtgp\webapp\test_realistic_face.png', 'wb') as f:
            f.write(base64.b64decode(res['data']))
        print('Captured test_realistic_face.png')

        # 2. Switch to Pixar Style
        send_cmd('Runtime.evaluate', {
            'expression': 'document.querySelector(\'.opt-btn[data-group="renderStyle"][data-val*="Pixar"]\').click();'
        })
        time.sleep(0.6)
        res = send_cmd('Page.captureScreenshot', {'format': 'png'})
        with open(r'C:\Users\USER\Downloads\webtgp\webapp\test_pixar_face.png', 'wb') as f:
            f.write(base64.b64decode(res['data']))
        print('Captured test_pixar_face.png')

        # 3. Switch to Full Body
        send_cmd('Runtime.evaluate', {
            'expression': 'document.getElementById("btnViewBody").click();'
        })
        time.sleep(0.6)
        res = send_cmd('Page.captureScreenshot', {'format': 'png'})
        with open(r'C:\Users\USER\Downloads\webtgp\webapp\test_pixar_body.png', 'wb') as f:
            f.write(base64.b64decode(res['data']))
        print('Captured test_pixar_body.png')

        # 4. Switch to Male Gender
        send_cmd('Runtime.evaluate', {
            'expression': 'document.querySelector(\'.opt-btn[data-group="gender"][data-val="Male"]\').click();'
        })
        time.sleep(0.6)
        res = send_cmd('Page.captureScreenshot', {'format': 'png'})
        with open(r'C:\Users\USER\Downloads\webtgp\webapp\test_male_pixar.png', 'wb') as f:
            f.write(base64.b64decode(res['data']))
        print('Captured test_male_pixar.png')

        # 5. Open Tab 5 (Model Sheet)
        send_cmd('Runtime.evaluate', {
            'expression': 'document.querySelector(\'.tab-btn[data-tab="tab-output"]\').click();'
        })
        time.sleep(0.6)
        res = send_cmd('Page.captureScreenshot', {'format': 'png'})
        with open(r'C:\Users\USER\Downloads\webtgp\webapp\test_tab5_grid.png', 'wb') as f:
            f.write(base64.b64decode(res['data']))
        print('Captured test_tab5_grid.png')

        print('ALL TESTS COMPLETED SUCCESSFULLY!')
finally:
    proc.terminate()
    try:
        shutil.rmtree(tmp_profile, ignore_errors=True)
    except:
        pass

"""SitRight dashboard: read-only ThingSpeak proxy. Python 3.9+, no pip packages."""
import json, os, re, urllib.request, urllib.parse, urllib.error, webbrowser, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config.json'
LOCK = threading.Lock()

def config():
    with LOCK:
        if CONFIG.exists():
            return json.loads(CONFIG.read_text(encoding='utf-8'))
        return {
            'channel_id': os.environ.get('THINGSPEAK_CHANNEL_ID', ''),
            'read_api_key': os.environ.get('THINGSPEAK_READ_API_KEY', ''),
            'demo_mode': os.environ.get('DEMO_MODE', 'true').lower() == 'true',
        }

def public_config(c):
    return {'channel_id': c.get('channel_id',''), 'has_read_key': bool(c.get('read_api_key')), 'demo_mode': bool(c.get('demo_mode',True))}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # No credentials in request paths; suppress routine poll logs.
        pass
    def send_json(self, data, status=200):
        b = json.dumps(data).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        path=urllib.parse.urlsplit(self.path).path
        if path=='/':
            b=(ROOT/'dashboard.html').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b); return
        if path=='/api/config':
            return self.send_json(public_config(config()))
        if path=='/api/feeds':
            c=config(); cid=str(c.get('channel_id',''))
            if not re.fullmatch(r'[1-9][0-9]{0,14}',cid): return self.send_json({'error':'Enter your ThingSpeak Channel ID in Connection settings.'},400)
            params={'results':100}
            if c.get('read_api_key'): params['api_key']=c['read_api_key']
            url=f'https://api.thingspeak.com/channels/{cid}/feeds.json?'+urllib.parse.urlencode(params)
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json'}),timeout=12) as r: data=json.load(r)
                if not isinstance(data,dict) or not isinstance(data.get('feeds'),list): raise ValueError('Unexpected cloud response')
                if str(data.get('channel',{}).get('id'))!=cid: raise ValueError('Channel mismatch')
                return self.send_json(data)
            except urllib.error.HTTPError as e:
                return self.send_json({'error':f'ThingSpeak HTTP {e.code}. Check Channel ID, sharing and Read API Key.'},502)
            except Exception:
                return self.send_json({'error':'Cannot read ThingSpeak. Check internet and channel settings.'},502)
        self.send_json({'error':'Not found'},404)
    def do_POST(self):
        if self.path!='/api/config': return self.send_json({'error':'Not found'},404)
        # Reject cross-origin browser writes while allowing same-origin hosts (localhost & Render).
        origin=self.headers.get('Origin')
        host=self.headers.get('Host')
        if origin and host and urllib.parse.urlsplit(origin).netloc!=host: return self.send_json({'error':'Origin not allowed'},403)
        if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.send_json({'error':'JSON required'},415)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<4096: raise ValueError()
            d=json.loads(self.rfile.read(length)); cid=str(d.get('channel_id','')).strip(); key=str(d.get('read_api_key','')).strip()
            if not re.fullmatch(r'[1-9][0-9]{0,14}',cid) or len(key)>128: raise ValueError()
            old=config()
            if not key and not d.get('clear_key') and cid==old.get('channel_id'): key=old.get('read_api_key','')
            new={'channel_id':cid,'read_api_key':key,'demo_mode':bool(d.get('demo_mode'))}
            with LOCK:
                tmp=CONFIG.with_suffix('.tmp')
                tmp.write_text(json.dumps(new,indent=2)+'\n',encoding='utf-8')
                tmp.replace(CONFIG)
            return self.send_json(public_config(new))
        except Exception: return self.send_json({'error':'Enter a numeric Channel ID and valid settings.'},400)

if __name__=='__main__':
    port=int(os.environ.get('PORT','8765'))
    host='0.0.0.0' if 'PORT' in os.environ else '127.0.0.1'
    url=f'http://{host}:{port}'; server=ThreadingHTTPServer((host,port),Handler)
    print('SitRight running at '+url+'\nPress Ctrl+C to stop.',flush=True)
    if 'PORT' not in os.environ:
        threading.Timer(0.8,lambda:webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()

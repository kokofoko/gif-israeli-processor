"""Bounded YouTube clip service; browser handles captioning and GIF encoding."""
import json, math, os, re, signal, subprocess, sys, tempfile, threading, time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ORIGIN = os.environ.get('SITE_ORIGIN', 'https://gif-israeli.kokofoko.chatgpt.site')
SLOTS = threading.BoundedSemaphore(2)
REQUESTS = defaultdict(deque)
LOCK = threading.Lock()


def validate(data):
    if not isinstance(data, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', str(data.get('videoId', ''))):
        raise ValueError('קישור הסרטון אינו תקין.')
    start, end = data.get('start'), data.get('end')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in (start, end)):
        raise ValueError('זמני החיתוך אינם תקינים.')
    if start < 0 or end - start < .2 or end - start > 8.001 or end > 43200:
        raise ValueError('בחר קטע באורך 0.2 עד 8 שניות.')
    return data['videoId'], start, end


def run(args, timeout):
    # Kill the whole group, including FFmpeg children, on timeout.
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(args, stdout=log, stderr=log, start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise RuntimeError('עיבוד הסרטון ארך יותר מדי זמן. נסה שוב או בחר סרטון אחר.')
        if code:
            log.seek(0); detail=log.read().decode(errors='replace')
            category = 'youtube_signin_required' if ('Sign in' in detail or 'not a bot' in detail) else 'upstream_forbidden' if '403' in detail else 'media_unavailable'
            print(json.dumps({'event':'processor_failure','category':category,'exit_code':code,'detail':re.sub(r'https?://\S+', '[URL]', detail)[-1800:]}),flush=True)
            # Upstream errors can contain signed media URLs. Never return logs to clients.
            raise RuntimeError('לא ניתן לשלוף את הסרטון מ־YouTube. ייתכן שהוא מוגבל או שהשליפה נחסמה.')


def normalize(source, target, duration):
    run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(source), '-map', '0:v:0',
         '-t', str(duration), '-an', '-sn', '-dn', '-vf', "scale='min(480,iw)':-2,fps=15",
         '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
         '-movflags', '+faststart', '-threads', '1', '-fs', '15000000', str(target)], 30)
    if not target.is_file() or target.stat().st_size < 100:
        raise RuntimeError('לא נוצר קטע וידאו תקין.')


def make_clip(video_id, start, end):
    with tempfile.TemporaryDirectory(prefix='gif-clip-') as folder:
        folder = Path(folder)
        # Canonical URL assembled from a strict video ID; no caller-controlled fetch URL/options.
        run([sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist',
             '--no-warnings', '--no-progress', '--socket-timeout', '12', '--retries', '1',
             '--fragment-retries', '1', '--concurrent-fragments', '1', '--max-filesize', '100M',
             '--js-runtimes', 'node', '--download-sections', f'*{start:.3f}-{end:.3f}',
             '--force-keyframes-at-cuts', '-f', 'bv[height<=480][ext=mp4]/bv[height<=480]/b[height<=480]',
             '--merge-output-format', 'mp4', '-o', str(folder / 'source.%(ext)s'),
             '--', f'https://www.youtube.com/watch?v={video_id}'], 110)
        sources = [f for f in folder.glob('source.*') if f.suffix in ('.mp4', '.webm', '.mkv')]
        if len(sources) != 1:
            raise RuntimeError('YouTube לא החזיר קטע וידאו זמין.')
        target = folder / 'clip.mp4'
        normalize(sources[0], target, end-start)
        return target.read_bytes()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, code, body, content_type='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if self.headers.get('Origin') == ORIGIN:
            self.send_header('Access-Control-Allow-Origin', ORIGIN)
            self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(200, {'status':'ok'}) if self.path == '/health' else self.reply(404, {'error':'Not found'})

    def do_OPTIONS(self):
        if self.headers.get('Origin') != ORIGIN:
            self.reply(403, {'error':'Origin denied'}); return
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '600')
        self.end_headers()

    def do_POST(self):
        if self.path != '/clip':
            self.reply(404, {'error':'Not found'}); return
        if self.headers.get('Origin') != ORIGIN:
            self.reply(403, {'error':'Origin denied'}); return
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self.reply(415, {'error':'JSON required'}); return
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 1024:
                raise ValueError('הבקשה גדולה מדי או ריקה.')
            args = validate(json.loads(self.rfile.read(length)))
        except (ValueError, TypeError) as error:
            self.reply(400, {'error':str(error)}); return
        with LOCK:
            now = time.monotonic()
            for key in list(REQUESTS):
                if not REQUESTS[key] or now - REQUESTS[key][-1] >= 60:
                    del REQUESTS[key]
            history = REQUESTS[self.client_address[0]]
            if len(history) >= 5:
                self.reply(429, {'error':'יותר מדי בקשות. נסה שוב בעוד דקה.'}); return
            history.append(now)
        if not SLOTS.acquire(blocking=False):
            self.reply(503, {'error':'שירות היצירה עסוק. נסה שוב בעוד רגע.'}); return
        try:
            self.reply(200, make_clip(*args), 'video/mp4')
        except RuntimeError as error:
            self.reply(502, {'error':str(error)})
        except Exception:
            self.reply(500, {'error':'היצירה נכשלה. נסה שוב.'})
        finally:
            SLOTS.release()


if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8080'))), Handler)
    server.socket.settimeout(15)
    server.serve_forever()

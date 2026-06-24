"""HeartGuard 音频代理 — 服务端绕过网易云限制，直接流式传输"""
import http.server
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PORT = 8765
ROOT = Path(__file__).parent

# --- 歌曲库（已全面核对 ID + 音频可用性）---
SONG_LIBRARY = {
    "good": [
        {"name": "七月上", "artist": "Jam", "id": "31445554"},
        {"name": "起风了", "artist": "买辣椒也用券", "id": "1330348068"},
        {"name": "海阔天空", "artist": "Beyond", "id": "346089"},
    ],
    "high": [
        {"name": "海阔天空", "artist": "Beyond", "id": "346089"},
        {"name": "七月上", "artist": "Jam", "id": "31445554"},
        {"name": "为了你 为了我", "artist": "Beyond", "id": "346090"},
    ],
    "low": [
        {"name": "起风了", "artist": "买辣椒也用券", "id": "1330348068"},
        {"name": "仓央嘉措情歌", "artist": "前冲", "id": "421934258"},
        {"name": "有多少爱可以重来", "artist": "周艳", "id": "340160"},
    ],
    "crisis": [
        {"name": "海阔天空", "artist": "Beyond", "id": "346089"},
        {"name": "有多少爱可以重来", "artist": "周艳", "id": "340160"},
        {"name": "为了你 为了我", "artist": "Beyond", "id": "346090"},
    ],
}


def fetch_audio(song_id):
    """获取音频数据：先直接外链，失败后尝试 API"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://music.163.com/",
    }

    # 方法1：直接外链
    try:
        url = f"https://music.163.com/song/media/outer/url?id={song_id}.mp3"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read()
            if len(data) > 200000:
                return data
    except Exception:
        pass

    # 方法2：内部 API 获取真实 URL
    try:
        api_url = f"https://music.163.com/api/song/enhance/player/url?id={song_id}&ids=[{song_id}]&br=320000"
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read())
            songs = result.get("data", [])
            if songs and songs[0].get("url"):
                real_url = songs[0]["url"]
                req2 = urllib.request.Request(real_url, headers=headers)
                with urllib.request.urlopen(req2, timeout=20) as resp2:
                    return resp2.read()
    except Exception:
        pass

    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # /api/library → 歌库
        if parsed.path == "/api/library":
            return self._json(SONG_LIBRARY)

        # /api/stream?id=XXX → 音频流
        if parsed.path == "/api/stream":
            params = urllib.parse.parse_qs(parsed.query)
            song_id = params.get("id", [None])[0]
            if not song_id:
                return self._error("missing id")

            audio = fetch_audio(song_id)
            if audio is None:
                return self._error("song not available", 502)

            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(audio)
            return

        # 默认：静态文件
        return super().do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, msg, code=400):
        body = json.dumps({"error": msg}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[proxy] {fmt % args}\n")


if __name__ == "__main__":
    import socketserver
    print(f"🎵 HeartGuard 代理 → http://localhost:{PORT}")
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 关闭")

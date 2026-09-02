from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import os

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run():
    port = int(os.getenv('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), Handler)
    server.serve_forever()

def keep_alive():
    t = Thread(target=run)
    t.start()

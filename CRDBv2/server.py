"""
CRDB Tracker Server
Serves static files + proxies requests to crdb3.amd.com (bypasses CORS).
"""

import http.server
import urllib.request
import urllib.error
import json
import os
import ssl
import subprocess
import shutil

PORT = 8091
DIRECTORY = os.path.dirname(os.path.abspath(__file__))


class CRDBProxyHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files and proxies /proxy?url=... requests to CRDB."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        if self.path.startswith('/proxy?'):
            self.handle_proxy()
        else:
            super().do_GET()

    def handle_proxy(self):
        """Proxy a request to an external URL (for CRDB page fetching)."""
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(self.path).query)
        target_url = params.get('url', [None])[0]

        if not target_url:
            self.send_error(400, 'Missing url parameter')
            return

        print(f'[proxy] Fetching: {target_url}')

        # Only allow proxying to crdb3.amd.com for security
        parsed = urlparse(target_url)
        if 'crdb3.amd.com' not in parsed.hostname:
            self.send_error(403, 'Only crdb3.amd.com URLs are allowed')
            return

        try:
            # Use curl.exe with --negotiate for Kerberos SSO authentication (Windows)
            # Must use full path to avoid PowerShell alias conflict
            curl_exe = r'C:\Windows\System32\curl.exe'
            if not os.path.exists(curl_exe):
                curl_exe = shutil.which('curl.exe') or shutil.which('curl')

            if curl_exe:
                result = subprocess.run(
                    [curl_exe, '-s', '-L', '--negotiate', '-u', ':',
                     '-k',  # skip SSL verify for internal certs
                     '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                     '-w', '\n%{http_code}',
                     '--max-time', '15',
                     target_url],
                    capture_output=True, timeout=20
                )
                output = result.stdout
                stderr = result.stderr.decode('utf-8', errors='replace').strip()
                if stderr:
                    print(f'[proxy] curl stderr for {target_url}: {stderr}')

                # Last line is the HTTP status code
                parts = output.rsplit(b'\n', 1)
                if len(parts) == 2:
                    html = parts[0]
                    status_code = int(parts[1].strip())
                else:
                    html = output
                    status_code = 200

                if status_code >= 400:
                    self.send_response(status_code)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': f'HTTP {status_code}'}).encode())
                    return

                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            else:
                # curl.exe not found — fallback to urllib (no auth — will likely get 401/404)
                print('[proxy] WARNING: curl.exe not found, falling back to urllib (no Kerberos auth)')
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(target_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                })
                resp = urllib.request.urlopen(req, timeout=15, context=ctx)
                html = resp.read()

                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(html)))
                self.end_headers()
                self.wfile.write(html)

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': f'HTTP {e.code}: {e.reason}'}).encode())

        except Exception as e:
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def log_message(self, format, *args):
        """Quieter logging — only show proxy requests and errors."""
        msg = format % args
        if '/proxy?' in msg or '404' in msg or '500' in msg or '502' in msg:
            super().log_message(format, *args)


if __name__ == '__main__':
    import socket
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = '0.0.0.0'

    print('=' * 48)
    print('  CRDB Status Tracker Server')
    print('=' * 48)
    print(f'  Local:   http://localhost:{PORT}/crdbtracker.html')
    print(f'  Network: http://{local_ip}:{PORT}/crdbtracker.html')
    print()
    print('  CRDB proxy enabled (bypasses CORS)')
    print('  Press Ctrl+C to stop.')
    print('=' * 48)
    print()

    server = http.server.HTTPServer(('0.0.0.0', PORT), CRDBProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
        server.server_close()

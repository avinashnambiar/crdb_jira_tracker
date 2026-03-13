"""
CRDB Tracker Server
Serves static files + proxies requests to crdb3.amd.com (bypasses CORS).
"""

import http.server
import socketserver
import urllib.request
import urllib.error
import json
import os
import ssl
import subprocess
import shutil
import threading

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

    def do_POST(self):
        if self.path.startswith('/proxy?'):
            self.handle_proxy(method='POST')
        else:
            self.send_error(405, 'POST only supported for /proxy')

    def do_OPTIONS(self):
        """Handle CORS preflight requests for custom headers like X-Jira-Auth."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'X-Jira-Auth, X-Twiki-Auth, Content-Type')
        self.send_header('Access-Control-Max-Age', '86400')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def handle_proxy(self, method='GET'):
        """Proxy a request to an external URL (for CRDB page fetching / TWiki save)."""
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(self.path).query)
        target_url = params.get('url', [None])[0]

        if not target_url:
            self.send_error(400, 'Missing url parameter')
            return

        # Read POST body if applicable
        post_body = None
        if method == 'POST':
            content_length = int(self.headers.get('Content-Length', 0))
            post_body = self.rfile.read(content_length) if content_length > 0 else b''

        print(f'[proxy] {method} {target_url}')

        # Only allow proxying to approved AMD domains for security
        parsed = urlparse(target_url)
        allowed_hosts = ['crdb3.amd.com', 'twiki.amd.com', 'amd.atlassian.net']
        if not any(host in parsed.hostname for host in allowed_hosts):
            self.send_error(403, 'Only crdb3.amd.com, twiki.amd.com, and amd.atlassian.net URLs are allowed')
            return

        # Determine auth method based on target host
        is_twiki = 'twiki.amd.com' in parsed.hostname
        is_jira = 'amd.atlassian.net' in parsed.hostname
        twiki_auth = self.headers.get('X-Twiki-Auth', '') if is_twiki else ''

        try:
            # Use curl.exe for HTTP requests
            # Must use full path to avoid PowerShell alias conflict
            curl_exe = r'C:\Windows\System32\curl.exe'
            if not os.path.exists(curl_exe):
                curl_exe = shutil.which('curl.exe') or shutil.which('curl')

            if curl_exe:
                # Build curl command based on target
                curl_cmd = [curl_exe, '-s', '-L',
                     '-k',  # skip SSL verify for internal certs
                     '-w', '\n%{http_code}',
                     '--max-time', '15']

                if is_jira:
                    # Jira Cloud — Accept JSON for API, use negotiate auth (corporate SSO)
                    curl_cmd.extend(['-H', 'Accept: application/json,text/html;q=0.9,*/*;q=0.8'])
                    # Try Jira API token if provided, otherwise negotiate
                    jira_auth = self.headers.get('X-Jira-Auth', '')
                    if jira_auth:
                        import base64
                        try:
                            creds = base64.b64decode(jira_auth).decode('utf-8')
                            curl_cmd.extend(['-u', creds])
                        except Exception:
                            curl_cmd.extend(['--negotiate', '-u', ':'])
                    else:
                        curl_cmd.extend(['--negotiate', '-u', ':'])
                else:
                    curl_cmd.extend(['-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'])

                if not is_jira:
                    # Auth for non-Jira targets (Jira auth is handled above)
                    if is_twiki and twiki_auth:
                        # TWiki uses Basic auth — credentials passed from browser
                        import base64
                        try:
                            creds = base64.b64decode(twiki_auth).decode('utf-8')
                            curl_cmd.extend(['-u', creds])
                        except Exception:
                            curl_cmd.extend(['--negotiate', '-u', ':'])
                    else:
                        # CRDB uses Kerberos SSO
                        curl_cmd.extend(['--negotiate', '-u', ':'])

                # Add POST data if this is a POST request
                if method == 'POST' and post_body is not None:
                    curl_cmd.extend(['-X', 'POST'])
                    # Write body to a temp file to avoid command-line length limits
                    import tempfile
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='wb')
                    tmp.write(post_body)
                    tmp.close()
                    curl_cmd.extend(['-d', f'@{tmp.name}'])
                    content_type_header = self.headers.get('Content-Type', 'application/x-www-form-urlencoded')
                    curl_cmd.extend(['-H', f'Content-Type: {content_type_header}'])

                curl_cmd.append(target_url)

                # Hide console window when running under pythonw (no parent console)
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE

                result = subprocess.run(
                    curl_cmd,
                    capture_output=True, timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    startupinfo=startupinfo
                )

                # Clean up temp file if created
                if method == 'POST' and post_body is not None:
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
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

                print(f'[proxy] Response: {status_code}, body size: {len(html)} bytes')

                if status_code >= 400:
                    self.send_response(status_code)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': f'HTTP {status_code}'}).encode())
                    return

                # Detect content type — JSON for Jira API, HTML otherwise
                content_type = 'text/html; charset=utf-8'
                if is_jira and (html.strip().startswith(b'{') or html.strip().startswith(b'[')):
                    content_type = 'application/json; charset=utf-8'

                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Headers', 'X-Jira-Auth, X-Twiki-Auth')
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

    server = socketserver.ThreadingTCPServer(('0.0.0.0', PORT), CRDBProxyHandler)
    server.allow_reuse_address = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
        server.server_close()

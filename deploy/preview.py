import os, threading, http.server, socketserver

class _Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, directory=None, **kw):
        super().__init__(*a, directory=directory or os.getcwd(), **kw)
    def log_message(self, *a): pass

def deploy_preview(project_dir, port):
    os.chdir(str(project_dir))
    httpd = socketserver.TCPServer(("", port), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return {"ok": True, "url": f"http://localhost:{port}", "port": port}

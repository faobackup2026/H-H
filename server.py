import json, os, re, sys, io, zipfile, time, threading, subprocess, shutil, signal, uuid, tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

HERE = Path(__file__).parent
PROJECTS = HERE / "projects"
PROJECTS.mkdir(exist_ok=True)
KEY = os.environ.get("GEMINI_API_KEY", "")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

os.chdir(str(HERE))

# ── In-memory store ──
projects = {}
tunnels = {}
deploy_jobs = {}

def load_projects():
    for d in PROJECTS.iterdir():
        if d.is_dir():
            meta = d / "meta.json"
            if meta.exists():
                p = json.loads(meta.read_text())
                projects[p["id"]] = p

load_projects()

def save_project_meta(p):
    d = PROJECTS / p["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(p, indent=2))

def new_id():
    return uuid.uuid4().hex[:12]

# ── Gemini API ──
def gemini_chat(messages):
    body = json.dumps({
        "contents": [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages],
        "systemInstruction": {"role": "user", "parts": [{"text": "Você é Hands & Head, IA da Fao Labs. Responda em português. Quando gerar sites, coloque o HTML COMPLETO em blocos ```html ... ``` e outros arquivos em ```css ``` ou ```js ```."}]},
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }).encode()
    req = urllib.request.Request(f"{API_URL}?key={KEY}", data=body, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
    return resp["candidates"][0]["content"]["parts"][0]["text"]

import urllib.request

def generate_website(prompt):
    """Extrai arquivos HTML/CSS/JS da resposta do Gemini e salva no projeto."""
    messages = [
        {"role": "user", "content": f"""Crie um site completo baseado nisto: {prompt}

Gere HTML, CSS e JS separados em blocos de código.
Use design moderno, responsivo, com ícones (Font Awesome via CDN).
Mínimo 3 arquivos: index.html, style.css, script.js.
Coloque cada arquivo em ```tipo ...``` com o nome do arquivo."""}
    ]
    reply = gemini_chat(messages)

    # Extrair arquivos dos blocos de código
    files = {}
    pattern = r'```(\w+)\s*\n(.*?)```'
    current_file = None
    for match in re.finditer(pattern, reply, re.DOTALL):
        lang = match.group(1).strip()
        code = match.group(2).strip()
        if lang in ('html', 'css', 'js', 'javascript', 'json'):
            if lang == 'html':
                files['index.html'] = code
            elif lang == 'css':
                files['style.css'] = code
            elif lang in ('js', 'javascript'):
                files['script.js'] = code
            elif lang == 'json':
                files['data.json'] = code

    if not files:
        # Tenta extrair HTML mesmo sem bloco
        html_match = re.search(r'<(!DOCTYPE|html|head|body)', reply)
        if html_match:
            files['index.html'] = reply

    return reply, files

def save_project_files(pid, files):
    pdir = PROJECTS / pid
    pdir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (pdir / name).write_text(content, encoding="utf-8")
    return pdir

# ── Deployment ──
def deploy_github_pages(pid):
    """Cria repo GitHub e faz deploy via GitHub Pages usando API."""
    p = projects.get(pid)
    if not p:
        return {"ok": False, "error": "Projeto não encontrado"}

    pdir = PROJECTS / pid
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return {"ok": False, "error": "GITHUB_TOKEN não configurado"}

    repo_name = f"hands-head-{pid}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }

    try:
        # Criar repo via API
        req = urllib.request.Request(
            "https://api.github.com/user/repos",
            data=json.dumps({"name": repo_name, "private": False, "auto_init": False}).encode(),
            headers={**headers, "Content-Type": "application/json"}
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        clone_url = resp["clone_url"].replace("https://", f"https://x-access-token:{token}@")

        # Git init, add, commit, push
        subprocess.run(["git", "init"], cwd=str(pdir), check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=str(pdir), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Deploy by Hands & Head"], cwd=str(pdir), check=True, capture_output=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=str(pdir), check=True, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", clone_url], cwd=str(pdir), check=True, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=str(pdir), check=True, capture_output=True, timeout=60)

        # Ativar GitHub Pages
        req2 = urllib.request.Request(
            f"https://api.github.com/repos/{resp['owner']['login']}/{repo_name}/pages",
            data=json.dumps({"source": {"branch": "main", "path": "/"}}).encode(),
            headers={**headers, "Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(req2).read()
        except:
            pass

        pages_url = f"https://{resp['owner']['login']}.github.io/{repo_name}"
        return {"ok": True, "url": pages_url, "repo": repo_name}

    except Exception as e:
        return {"ok": False, "error": str(e)}

def deploy_localtunnel(pid):
    """Expoe projeto via localtunnel (npx)."""
    p = projects.get(pid)
    if not p:
        return {"ok": False, "error": "Projeto não encontrado"}

    port = 9000 + hash(pid) % 1000
    pdir = PROJECTS / pid

    # Server thread
    def serve():
        os.chdir(str(pdir))
        httpd = HTTPServer(("", port), lambda *a: SimpleHTTPRequestHandler(*a, directory=str(pdir)))
        httpd.serve_forever()

    import http.server
    class SimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, directory=None, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)
        def log_message(self, fmt, *args):
            pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    time.sleep(1)

    # localtunnel via npx
    try:
        proc = subprocess.Popen(
            ["npx", "localtunnel", "--port", str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        time.sleep(5)
        # LT prints URL to stderr
        stderr = ""
        try:
            _, stderr = proc.communicate(timeout=3)
        except:
            proc.terminate()
        url_match = re.search(r'(https?://[^\s]+)', stderr)
        if url_match:
            return {"ok": True, "url": url_match.group(1), "port": port}
        return {"ok": True, "url": f"http://localhost:{port}", "port": port, "note": "Tunnel failed, local only"}
    except Exception as e:
        return {"ok": True, "url": f"http://localhost:{port}", "port": port, "note": f"Tunnel: {e}"}

def deploy_cloudflare(pid):
    p = projects.get(pid)
    if not p:
        return {"ok": False, "error": "Projeto não encontrado"}
    pdir = PROJECTS / pid
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not token:
        return {"ok": False, "error": "CLOUDFLARE_API_TOKEN não configurado"}
    name = f"hands-head-{pid[:8]}"

    env = {**os.environ, "CLOUDFLARE_API_TOKEN": token, "CLOUDFLARE_ACCOUNT_ID": os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")}

    try:
        # Create project (fails silently if exists)
        subprocess.run(
            ["npx.cmd", "wrangler", "pages", "project", "create", name, "--production-branch", "main"],
            capture_output=True, text=True, timeout=30, env=env, cwd=str(pdir)
        )

        # Deploy
        result = subprocess.run(
            ["npx.cmd", "wrangler", "pages", "deploy", str(pdir), "--project-name", name, "--branch", "main"],
            capture_output=True, text=True, timeout=120, env=env, cwd=str(HERE)
        )
        out = result.stdout + result.stderr

        # Extract URL from output
        import re
        url_match = re.search(r'(https://[a-zA-Z0-9-]+\.pages\.dev)', out)
        if url_match:
            url = url_match.group(1)
        else:
            url = f"https://{name}.pages.dev"

        if result.returncode == 0:
            return {"ok": True, "url": url, "method": "cloudflare"}
        else:
            return {"ok": False, "error": out[:500]}

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timeout no deploy Cloudflare"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def deploy_preview(pid):
    """Apenas server local."""
    port = 9100 + int(hash(pid) % 900) if pid else 9100
    pdir = PROJECTS / pid

    import http.server
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(pdir), **kwargs)
        def log_message(self, fmt, *args):
            pass

    httpd = HTTPServer(("", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return {"ok": True, "url": f"http://localhost:{port}", "port": port}

# ── HTTP Server ──
class APIHandler(BaseHTTPRequestHandler):
    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _html(self, content, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length:
                raw = self.rfile.read(length)
                return json.loads(raw.decode()) if raw.strip() else {}
            return {}
        except Exception:
            return {}

    def do_OPTIONS(self):
        self._json({})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/health":
            self._json({"status": "ok", "projects": len(projects)})

        elif path == "/api/projects":
            self._json({"projects": list(projects.values())})

        elif path.startswith("/api/projects/"):
            pid = path.split("/")[-1]
            p = projects.get(pid)
            if not p:
                self._json({"error": "not found"}, 404)
                return
            pdir = PROJECTS / pid
            files = {}
            for f in pdir.iterdir():
                if f.is_file() and f.suffix in (".html", ".css", ".js", ".json", ".png", ".jpg", ".svg"):
                    files[f.name] = f.read_text(encoding="utf-8") if f.suffix != ".png" else ""
            self._json({"project": p, "files": files})

        elif path.startswith("/api/deploy-status"):
            pid = parse_qs(parsed.query).get("pid", [None])[0]
            status = deploy_jobs.get(pid, {"status": "unknown"})
            self._json(status)

        elif path == "/" or path == "":
            self._html((HERE / "index.html").read_text(encoding="utf-8"))

        else:
            # Try static file
            fpath = HERE / path.lstrip("/")
            if fpath.exists() and fpath.is_file():
                self.send_response(200)
                if fpath.suffix == ".html":
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                elif fpath.suffix == ".css":
                    self.send_header("Content-Type", "text/css")
                elif fpath.suffix == ".js":
                    self.send_header("Content-Type", "application/javascript")
                elif fpath.suffix == ".png":
                    self.send_header("Content-Type", "image/png")
                else:
                    self.send_header("Content-Type", "application/octet-stream")
                self.end_headers()
                self.wfile.write(fpath.read_bytes())
            else:
                self._json({"error": "not found"}, 404)

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            body = self._read_body()

            if path == "/api/chat":
                prompt = body.get("message", "")
                if not prompt:
                    self._json({"error": "mensagem vazia"}, 400)
                    return

                pid = body.get("projectId") or new_id()
                is_new = pid not in projects
                if is_new:
                    projects[pid] = {
                        "id": pid, "title": prompt[:50], "messages": [], "files": {},
                        "created": time.time(), "deployUrl": None, "status": "created"
                    }
                p = projects[pid]
                p["messages"].append({"role": "user", "content": prompt})

                try:
                    reply, files = generate_website(prompt)
                    p["messages"].append({"role": "assistant", "content": reply})
                    p["files"] = {**p.get("files", {}), **{k: True for k in files}}
                    save_project_files(pid, files)
                    p["status"] = "generated"
                    save_project_meta(p)
                    self._json({
                        "projectId": pid, "reply": reply,
                        "files": list(files.keys()), "isNew": is_new, "project": p
                    })
                except Exception as e:
                    p["status"] = "error"
                    self._json({"error": str(e), "projectId": pid}, 500)
                return

            if path == "/api/deploy":
                pid = body.get("projectId", "")
                method = body.get("method", "preview")
                p = projects.get(pid)
                if not p:
                    self._json({"error": "not found"}, 404)
                    return

                # Override CF credentials from headers if provided
                cf_token = self.headers.get("X-CF-Token", "")
                cf_account = self.headers.get("X-CF-Account", "")
                if cf_token:
                    os.environ["CLOUDFLARE_API_TOKEN"] = cf_token
                if cf_account:
                    os.environ["CLOUDFLARE_ACCOUNT_ID"] = cf_account

                deploy_jobs[pid] = {"status": "deploying", "method": method}

                def do_deploy():
                    try:
                        if method == "github":
                            result = deploy_github_pages(pid)
                        elif method == "tunnel":
                            result = deploy_localtunnel(pid)
                        elif method == "cloudflare":
                            result = deploy_cloudflare(pid)
                        else:
                            result = deploy_preview(pid)
                        if result.get("ok"):
                            p["deployUrl"] = result["url"]
                            p["status"] = "deployed"
                            p["deployMethod"] = method
                            save_project_meta(p)
                            deploy_jobs[pid] = {"status": "done", "url": result["url"], "method": method}
                        else:
                            deploy_jobs[pid] = {"status": "error", "error": result.get("error", "unknown"), "method": method}
                    except Exception as e:
                        deploy_jobs[pid] = {"status": "error", "error": str(e), "method": method}

                t = threading.Thread(target=do_deploy, daemon=True)
                t.start()
                self._json({"status": "deploying", "projectId": pid, "method": method})
                return

            if path == "/api/new":
                pid = new_id()
                projects[pid] = {
                    "id": pid, "title": "Nova conversa", "messages": [], "files": {},
                    "created": time.time(), "deployUrl": None, "status": "created"
                }
                save_project_meta(projects[pid])
                self._json({"projectId": pid, "project": projects[pid]})
                return

            self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)


def main():
    import http.server
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3001

    if not KEY:
        print("ERRO: Defina GEMINI_API_KEY")
        print("  $env:GEMINI_API_KEY = 'sua-chave'")
        sys.exit(1)

    try:
        server = HTTPServer(("0.0.0.0", port), APIHandler)
    except OSError as e:
        print(f"ERRO: Porta {port} ocupada: {e}")
        print("Tente: python server.py 3002")
        sys.exit(1)

    print(f"+{'-'*46}+")
    print(f"|  Hands & Head by Fao Labs  -  Server     |")
    print(f"|{'-'*46}|")
    print(f"|  API:  http://localhost:{port}/api        |")
    print(f"|  UI:   http://localhost:{port}            |")
    print(f"|  Proj: {PROJECTS}                        |")
    print(f"+{'-'*46}+")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor parado.")
        server.server_close()

if __name__ == "__main__":
    main()

import json, os, re, sys, io, time, threading, subprocess, shutil, uuid, socketserver, http.server, urllib.request, urllib.error
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).parent
PROJECTS = HERE / "projects"
SESSIONS = HERE / "sessions"
PROJECTS.mkdir(exist_ok=True)
SESSIONS.mkdir(exist_ok=True)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
OLLAMA_URL = "http://localhost:11434/api/chat"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

os.chdir(str(HERE))

sessions = {}
projects = {}
deploy_jobs = {}
stream_buffers = {}

def new_id():
    return uuid.uuid4().hex[:12]

def load_sessions():
    for f in SESSIONS.iterdir():
        if f.suffix == ".json":
            try:
                s = json.loads(f.read_text())
                sessions[s["id"]] = s
            except: pass

def save_session(s):
    (SESSIONS / f"{s['id']}.json").write_text(json.dumps(s, indent=2))

def load_projects():
    for d in PROJECTS.iterdir():
        if d.is_dir():
            meta = d / "meta.json"
            if meta.exists():
                try:
                    p = json.loads(meta.read_text())
                    projects[p["id"]] = p
                except: pass

def save_project_meta(p):
    d = PROJECTS / p["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(p, indent=2))

load_sessions()
load_projects()

# ── Ollama Chat ──

def ollama_chat(messages, model="qwen3:4b"):
    body = json.dumps({"model": model, "messages": messages, "stream": False, "options": {"num_predict": 2048}}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
        return resp.get("message", {}).get("content", "")
    except Exception as e:
        return f"Erro Ollama: {e}"

def ollama_stream(messages, model="qwen3:4b"):
    body = json.dumps({"model": model, "messages": messages, "stream": True, "options": {"num_predict": 2048}}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=180)
        for line in resp:
            if line.strip():
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        break
                except: pass
    except Exception as e:
        yield f"\n[Erro: {e}]"

# ── Gemini Chat ──

def gemini_chat(messages):
    if not GEMINI_KEY:
        return "ERRO: GEMINI_API_KEY não configurada"
    body = json.dumps({
        "contents": [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages],
        "systemInstruction": {"role": "user", "parts": [{"text": "Você é Hands & Head, IA da Fao Labs. Responda em português."}]},
        "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
    }).encode()
    req = urllib.request.Request(f"{GEMINI_URL}?key={GEMINI_KEY}", data=body, headers={"Content-Type": "application/json"})
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
        return resp["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Erro Gemini: {e}"

# ── Website Generation ──

def extract_files(reply):
    files = {}
    for match in re.finditer(r'```(\w+)\s*\n(.*?)```', reply, re.DOTALL):
        lang = match.group(1).strip()
        code = match.group(2).strip()
        if lang == 'html': files['index.html'] = code
        elif lang == 'css': files['style.css'] = code
        elif lang in ('js', 'javascript'): files['script.js'] = code
        elif lang == 'json': files['data.json'] = code
    if not files:
        if re.search(r'<(!DOCTYPE|html|head|body)', reply):
            files['index.html'] = reply
    return files

def generate_website(prompt):
    messages = [{"role": "user", "content": f"""Crie um site completo baseado nisto: {prompt}

Gere HTML, CSS e JS separados em blocos de código.
Use design moderno, responsivo, com ícones (Font Awesome via CDN).
Mínimo 3 arquivos: index.html, style.css, script.js.
Coloque cada arquivo em ```tipo ...``` com o nome do arquivo."""}]
    reply = gemini_chat(messages)
    files = extract_files(reply)
    return reply, files

def save_project_files(pid, files):
    pdir = PROJECTS / pid
    pdir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (pdir / name).write_text(content, encoding="utf-8")
    return pdir

# ── Agent Tools ──

from tools import tools_registry

def execute_tool(name, params):
    return tools_registry.execute(name, **params)

# ── Deploy ──

def deploy_preview(pid):
    p = projects.get(pid)
    if not p: return {"ok": False, "error": "Projeto não encontrado"}
    pdir = PROJECTS / pid
    port = 9100 + int(hash(pid) % 900)
    os.chdir(str(pdir))
    from http.server import SimpleHTTPRequestHandler
    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(pdir), **kw)
        def log_message(self, *a): pass
    httpd = socketserver.TCPServer(("", port), H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return {"ok": True, "url": f"http://localhost:{port}", "port": port}

def deploy_github(pid):
    p = projects.get(pid)
    if not p: return {"ok": False, "error": "Projeto não encontrado"}
    if not GITHUB_TOKEN: return {"ok": False, "error": "GITHUB_TOKEN não configurado"}
    pdir = PROJECTS / pid
    repo_name = f"site-{pid[:8]}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    try:
        req = urllib.request.Request(
            "https://api.github.com/user/repos",
            data=json.dumps({"name": repo_name, "private": False, "auto_init": False}).encode(),
            headers={**headers, "Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            if e.code != 422: return {"ok": False, "error": f"GitHub API: {e.code}"}
    except Exception as e:
        return {"ok": False, "error": f"GitHub API: {e}"}
    clone_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/faobackup2026/{repo_name}.git"
    try:
        subprocess.run(["git", "init"], cwd=str(pdir), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "bot@faolabs.com"], cwd=str(pdir), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "FAO Bot"], cwd=str(pdir), capture_output=True, timeout=10)
        subprocess.run(["git", "add", "-A"], cwd=str(pdir), capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "Deploy by Hands & Head"], cwd=str(pdir), capture_output=True, timeout=10)
        subprocess.run(["git", "branch", "-M", "main"], cwd=str(pdir), capture_output=True, timeout=10)
        subprocess.run(["git", "remote", "add", "origin", clone_url], cwd=str(pdir), capture_output=True, timeout=10)
        pr = subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=str(pdir), capture_output=True, text=True, timeout=60)
        if pr.returncode != 0: return {"ok": False, "error": pr.stderr[:500]}
        return {"ok": True, "url": f"https://github.com/faobackup2026/{repo_name}", "method": "github"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def deploy_localtunnel(pid):
    p = projects.get(pid)
    if not p: return {"ok": False, "error": "Projeto não encontrado"}
    pdir = PROJECTS / pid
    port = 9000 + hash(pid) % 1000
    os.chdir(str(pdir))
    from http.server import SimpleHTTPRequestHandler
    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(pdir), **kw)
        def log_message(self, *a): pass
    httpd = socketserver.TCPServer(("", port), H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    try:
        proc = subprocess.Popen(["npx", "localtunnel", "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(4)
        try: _, se = proc.communicate(timeout=3)
        except: proc.terminate()
        url_m = re.search(r'(https?://[^\s]+)', se or "")
        if url_m: return {"ok": True, "url": url_m.group(1), "method": "tunnel"}
    except: pass
    return {"ok": True, "url": f"http://localhost:{port}", "method": "local", "note": "Tunnel indisponível"}

# ── SSE Streaming ──

class StreamBuffer:
    def __init__(self):
        self.buffer = []
        self.event = threading.Event()
        self.done = False

    def add(self, text):
        self.buffer.append(text)
        self.event.set()

    def finish(self):
        self.done = True
        self.event.set()

    def get_and_clear(self):
        out = "".join(self.buffer)
        self.buffer.clear()
        self.event.clear()
        return out

# ── HTTP Server ──

MIME_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript",
    ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
    ".ico": "image/x-icon", ".woff2": "font/woff2",
}

class Handler(http.server.BaseHTTPRequestHandler):
    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Session-Id")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _html(self, content, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length:
                raw = self.rfile.read(length)
                text = raw.decode("utf-8")
                return json.loads(text) if text.strip() else {}
            return {}
        except Exception as e:
            print(f"[debug] _body error: {e}")
            return {}

    def _file(self, path, status=200):
        p = HERE / path
        if p.exists() and p.is_file():
            self.send_response(status)
            ext = p.suffix.lower()
            self.send_header("Content-Type", MIME_TYPES.get(ext, "application/octet-stream"))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(p.read_bytes())
            return True
        return False

    def do_OPTIONS(self):
        self._json({})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        if path == "/api/health":
            self._json({"status": "ok", "sessions": len(sessions), "projects": len(projects), "gemini": bool(GEMINI_KEY), "github": bool(GITHUB_TOKEN)})

        elif path == "/api/sessions":
            self._json({"sessions": [{"id": s["id"], "title": s.get("title", ""), "created": s.get("created", 0)} for s in sessions.values()]})

        elif path.startswith("/api/sessions/"):
            sid = path.split("/")[-1]
            s = sessions.get(sid)
            if not s: self._json({"error": "not found"}, 404)
            else: self._json({"session": s})

        elif path == "/api/projects":
            self._json({"projects": list(projects.values())})

        elif path.startswith("/api/projects/"):
            pid = path.split("/")[-1]
            p = projects.get(pid)
            if not p: self._json({"error": "not found"}, 404)
            else:
                pdir = PROJECTS / pid
                files = {}
                for f in pdir.iterdir():
                    if f.is_file() and f.suffix in (".html", ".css", ".js", ".json", ".png", ".jpg", ".svg"):
                        files[f.name] = f.read_text(encoding="utf-8") if f.suffix not in (".png", ".jpg") else ""
                self._json({"project": p, "files": files})

        elif path == "/api/deploy-status":
            pid = qs.get("pid", [None])[0]
            self._json(deploy_jobs.get(pid, {"status": "unknown"}))

        elif path == "/api/stream":
            sid = qs.get("session", [None])[0]
            stream_id = qs.get("id", [None])[0]
            key = f"{sid}_{stream_id}" if sid and stream_id else None
            buf = stream_buffers.get(key)
            if not buf:
                self._json({"error": "stream not found"}, 404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while not buf.done or buf.buffer:
                    text = buf.get_and_clear()
                    if text:
                        for line in text.split("\n"):
                            self.wfile.write(f"data: {json.dumps(line)}\n\n".encode())
                        self.wfile.flush()
                    if not buf.done:
                        buf.event.wait(timeout=1)
                self.wfile.write("data: [DONE]\n\n".encode())
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        elif path == "/api/tools":
            self._json({"tools": tools_registry.list()})

        elif path in ("/", ""):
            self._html((HERE / "index.html").read_text(encoding="utf-8"))
            return

        elif path.startswith("/projects/"):
            file_path = path.lstrip("/")
            if self._file(HERE / file_path): return
            self._json({"error": "not found"}, 404)
            return

        else:
            if self._file(HERE / path.lstrip("/")): return
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            body = self._body()
            sid = self.headers.get("X-Session-Id", body.get("sessionId", ""))

            # ── Chat (Ollama) ──
            if path == "/api/chat":
                message = body.get("message", "")
                if not message: self._json({"error": "mensagem vazia"}, 400); return
                model = body.get("model", "qwen3:4b")
                stream = body.get("stream", False)
                if not sid:
                    sid = new_id()
                    sessions[sid] = {"id": sid, "title": message[:50], "messages": [], "created": time.time()}
                s = sessions[sid]
                s["messages"].append({"role": "user", "content": message})
                s.setdefault("title", message[:50])

                if stream:
                    stream_id = new_id()
                    key = f"{sid}_{stream_id}"
                    buf = StreamBuffer()
                    stream_buffers[key] = buf
                    def run():
                        msgs = [{"role": "system", "content": "Você é Hands & Head, assistente de IA da Fao Labs. Responda em português. Use ```tool nome_ferramenta``` para executar ferramentas quando necessário."}]
                        for m in s["messages"]: msgs.append({"role": m["role"], "content": m["content"]})
                        full = ""
                        for token in ollama_stream(msgs, model):
                            full += token
                            buf.add(token)
                        s["messages"].append({"role": "assistant", "content": full})
                        save_session(s)
                        buf.finish()
                    threading.Thread(target=run, daemon=True).start()
                    self._json({"ok": True, "sessionId": sid, "streamId": stream_id})
                else:
                    msgs = [{"role": "system", "content": "Você é Hands & Head, assistente de IA da Fao Labs. Responda em português."}]
                    for m in s["messages"]: msgs.append({"role": m["role"], "content": m["content"]})
                    reply = ollama_chat(msgs, model)
                    s["messages"].append({"role": "assistant", "content": reply})
                    save_session(s)
                    self._json({"ok": True, "reply": reply, "sessionId": sid})
                return

            # ── Gemini Chat (for website gen) ──
            if path == "/api/gemini":
                message = body.get("message", "")
                if not message: self._json({"error": "mensagem vazia"}, 400); return
                msgs = [{"role": "user", "content": message}]
                reply = gemini_chat(msgs)
                self._json({"ok": True, "reply": reply})
                return

            # ── Generate Website ──
            if path == "/api/generate":
                prompt = body.get("prompt", "")
                if not prompt: self._json({"error": "prompt vazio"}, 400); return
                pid = body.get("projectId") or new_id()
                is_new = pid not in projects
                if is_new:
                    projects[pid] = {"id": pid, "title": prompt[:50], "created": time.time(), "deployUrl": None, "status": "created"}
                p = projects[pid]
                try:
                    reply, files = generate_website(prompt)
                    save_project_files(pid, files)
                    p["status"] = "generated"
                    save_project_meta(p)
                    self._json({"ok": True, "projectId": pid, "reply": reply, "files": list(files.keys()), "isNew": is_new})
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return

            # ── Execute Tool ──
            if path == "/api/tools/execute":
                tool_name = body.get("tool", "")
                params = body.get("params", {})
                result = execute_tool(tool_name, params)
                self._json(result)
                return

            # ── Deploy ──
            if path == "/api/deploy":
                pid = body.get("projectId", "")
                method = body.get("method", "preview")
                p = projects.get(pid)
                if not p: self._json({"error": "not found"}, 404); return
                deploy_jobs[pid] = {"status": "deploying", "method": method}
                def do_deploy():
                    try:
                        if method == "github": result = deploy_github(pid)
                        elif method == "tunnel": result = deploy_localtunnel(pid)
                        else: result = deploy_preview(pid)
                        if result.get("ok"):
                            p["deployUrl"] = result["url"]
                            p["status"] = "deployed"
                            p["deployMethod"] = method
                            save_project_meta(p)
                            deploy_jobs[pid] = {"status": "done", "url": result["url"], "method": method}
                        else:
                            deploy_jobs[pid] = {"status": "error", "error": result.get("error", "unknown")}
                    except Exception as e:
                        deploy_jobs[pid] = {"status": "error", "error": str(e)}
                threading.Thread(target=do_deploy, daemon=True).start()
                self._json({"status": "deploying", "projectId": pid, "method": method})
                return

            # ── New Conversation ──
            if path == "/api/new":
                sid = new_id()
                sessions[sid] = {"id": sid, "title": "Nova conversa", "messages": [], "created": time.time()}
                save_session(sessions[sid])
                self._json({"ok": True, "sessionId": sid})
                return

            # ── New Project ──
            if path == "/api/new-project":
                pid = new_id()
                projects[pid] = {"id": pid, "title": "Novo projeto", "created": time.time(), "deployUrl": None, "status": "created"}
                save_project_meta(projects[pid])
                self._json({"ok": True, "projectId": pid})
                return

            # ── Save File ──
            if path == "/api/save-file":
                pid = body.get("projectId", "")
                name = body.get("name", "")
                content = body.get("content", "")
                if not pid or not name: self._json({"error": "projectId e name obrigatórios"}, 400); return
                pdir = PROJECTS / pid
                pdir.mkdir(parents=True, exist_ok=True)
                (pdir / name).write_text(content, encoding="utf-8")
                self._json({"ok": True})
                return

            self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3001
    if not GEMINI_KEY:
        print("AVISO: GEMINI_API_KEY não configurada - geração de sites não funcionará")
    print(f"+{'-'*46}+")
    print(f"|  Hands & Head by Fao Labs  -  v2.0           |")
    print(f"|{'-'*46}|")
    print(f"|  UI:   http://localhost:{port}               |")
    print(f"|  API:  http://localhost:{port}/api           |")
    print(f"|  Chat: Ollama (qwen3:4b)                    |")
    print(f"|  Web:  Gemini 2.5 Flash                     |")
    print(f"|  Git:  {'OK' if GITHUB_TOKEN else '--'} GitHub Token                      |")
    print(f"+{'-'*46}+")
    try:
        server = socketserver.TCPServer(("0.0.0.0", port), Handler)
        server.serve_forever()
    except OSError as e:
        print(f"ERRO: Porta {port} ocupada: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nServidor parado.")
        server.server_close()

if __name__ == "__main__":
    main()

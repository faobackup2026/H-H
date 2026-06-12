import json, urllib.request, threading
from urllib.request import Request

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen3:4b"

def chat(messages, model=DEFAULT_MODEL, stream_callback=None):
    body = json.dumps({
        "model": model,
        "messages": messages,
        "stream": stream_callback is not None,
        "options": {"num_predict": 2048}
    }).encode()
    req = Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=120)
    if stream_callback:
        full = ""
        for line in resp:
            if line.strip():
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    full += content
                    stream_callback(content)
                    if chunk.get("done"):
                        break
                except:
                    pass
        return full
    else:
        data = json.loads(resp.read())
        return data.get("message", {}).get("content", "")

def stream(messages, model=DEFAULT_MODEL):
    q = []
    e = threading.Event()
    def cb(tok):
        q.append(tok)
        e.set()
    def wait():
        thread = threading.Thread(target=lambda: chat(messages, model, cb), daemon=True)
        thread.start()
    wait()
    return q, e

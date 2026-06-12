import json, os, re, urllib.request
from urllib.request import Request

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

def get_key():
    return os.environ.get("GEMINI_API_KEY", "")

def chat(messages):
    key = get_key()
    if not key:
        return "ERRO: GEMINI_API_KEY não configurada"
    body = json.dumps({
        "contents": [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages],
        "systemInstruction": {"role": "user", "parts": [{"text": "Você é Hands & Head, IA da Fao Labs. Responda em português. Quando gerar sites, coloque o HTML COMPLETO em blocos ```html ... ``` e outros arquivos em ```css ``` ou ```js ```."}]},
        "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
    }).encode()
    req = Request(f"{API_URL}?key={key}", data=body, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
    return resp["candidates"][0]["content"]["parts"][0]["text"]

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
        html_match = re.search(r'<(!DOCTYPE|html|head|body)', reply)
        if html_match: files['index.html'] = reply
    return files

def generate_website(prompt):
    messages = [{"role": "user", "content": f"""Crie um site completo baseado nisto: {prompt}

Gere HTML, CSS e JS separados em blocos de código.
Use design moderno, responsivo, com ícones (Font Awesome via CDN).
Mínimo 3 arquivos: index.html, style.css, script.js.
Coloque cada arquivo em ```tipo ...``` com o nome do arquivo."""}]
    reply = chat(messages)
    files = extract_files(reply)
    return reply, files

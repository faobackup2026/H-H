import os
from pathlib import Path

class FileEditorTool:
    name = "file_editor"
    description = "Lê, escreve e edita arquivos"

    def execute(self, path, operation="read", content=None):
        p = Path(path)
        try:
            if operation == "read":
                if not p.exists():
                    return {"success": False, "error": "Arquivo não encontrado"}
                return {"success": True, "content": p.read_text(encoding="utf-8")[:5000]}
            elif operation == "write":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content or "", encoding="utf-8")
                return {"success": True, "content": f"Arquivo salvo: {p}"}
            elif operation == "list_dir":
                if not p.exists() or not p.is_dir():
                    return {"success": False, "error": "Diretório não encontrado"}
                items = [{"name": f.name, "type": "dir" if f.is_dir() else "file"} for f in p.iterdir()]
                return {"success": True, "items": items}
            else:
                return {"success": False, "error": f"Operação desconhecida: {operation}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

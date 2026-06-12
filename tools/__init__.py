from .terminal import TerminalTool
from .file_editor import FileEditorTool
from .think import ThinkTool

class ToolsRegistry:
    def __init__(self):
        self._tools = {}
        self._register("terminal", TerminalTool())
        self._register("file_editor", FileEditorTool())
        self._register("think", ThinkTool())

    def _register(self, name, tool):
        self._tools[name] = tool

    def get(self, name):
        return self._tools.get(name)

    def list(self):
        return list(self._tools.keys())

    def execute(self, name, **kwargs):
        tool = self.get(name)
        if not tool:
            return {"error": f"Ferramenta '{name}' não encontrada"}
        try:
            return tool.execute(**kwargs)
        except Exception as e:
            return {"error": str(e)}

tools_registry = ToolsRegistry()

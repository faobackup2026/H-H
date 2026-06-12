class ThinkTool:
    name = "think"
    description = "Raciocínio interno do agente"

    def execute(self, thought=""):
        return {"success": True, "content": f"Pensamento registrado: {thought[:500]}"}

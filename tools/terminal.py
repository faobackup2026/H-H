import subprocess, os

class TerminalTool:
    name = "terminal"
    description = "Executa comandos no terminal"

    def execute(self, command, working_dir=None, timeout=60):
        try:
            cwd = working_dir or os.getcwd()
            result = subprocess.run(
                command, shell=True, cwd=cwd,
                capture_output=True, text=True, timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[-3000:],
                "stderr": result.stderr[-1000:],
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timeout após {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}

import os, subprocess, json, urllib.request

def deploy_github(project_dir, repo_name=None, token=None, account=None):
    token = token or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return {"ok": False, "error": "GITHUB_TOKEN não configurado"}
    account = account or "faobackup2026"
    repo_name = repo_name or f"site-{os.path.basename(str(project_dir))[:8]}"
    try:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        req = urllib.request.Request(
            "https://api.github.com/user/repos",
            data=json.dumps({"name": repo_name, "private": False, "auto_init": False}).encode(),
            headers={**headers, "Content-Type": "application/json"}
        )
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        if e.code != 422:
            return {"ok": False, "error": f"GitHub API: {e.code}"}
    clone_url = f"https://x-access-token:{token}@github.com/{account}/{repo_name}.git"
    try:
        subprocess.run(["git", "init"], cwd=str(project_dir), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "bot@faolabs.com"], cwd=str(project_dir), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "FAO Bot"], cwd=str(project_dir), capture_output=True, timeout=10)
        subprocess.run(["git", "add", "-A"], cwd=str(project_dir), capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "Deploy by Hands & Head"], cwd=str(project_dir), capture_output=True, timeout=10)
        subprocess.run(["git", "branch", "-M", "main"], cwd=str(project_dir), capture_output=True, timeout=10)
        subprocess.run(["git", "remote", "add", "origin", clone_url], cwd=str(project_dir), capture_output=True, timeout=10)
        pr = subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=str(project_dir), capture_output=True, text=True, timeout=60)
        if pr.returncode != 0:
            return {"ok": False, "error": pr.stderr[:500]}
        return {"ok": True, "url": f"https://github.com/{account}/{repo_name}", "repo": repo_name}
    except Exception as e:
        return {"ok": False, "error": str(e)}

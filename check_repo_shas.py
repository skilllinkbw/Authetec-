import subprocess, sys, os
sys.stdout.reconfigure(encoding='utf-8')
BASE = r"C:\Users\DELL\Documents\GitHub\Authetec-\benchmarks"
repos = ["repo1_lightgbm", "repo2_ensemble", "repo3_pipeline",
         "repo4_insurance", "repo5_graph", "repo6_identity"]
for name in repos:
    path = os.path.join(BASE, name)
    if not os.path.isdir(path):
        print(f"  [{name}] MISSING")
        continue
    try:
        out = subprocess.run(
            ["git", "-C", path, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=15
        )
        head = out.stdout.strip() if out.returncode == 0 else ("NO-GIT " + out.stderr.strip())
    except Exception as e:
        head = f"ERR {e}"
    lic = os.path.exists(os.path.join(path, "LICENSE"))
    remotes = ""
    try:
        r = subprocess.run(["git", "-C", path, "remote", "-v"], capture_output=True, text=True, timeout=10)
        remotes = r.stdout.strip()[:120]
    except Exception:
        pass
    print(f"[{name}] HEAD={head[:40]}")
    print(f"     license_file={'yes' if lic else 'no'}  remote={remotes}")
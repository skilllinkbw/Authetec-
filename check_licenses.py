import os, glob, re, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = r"C:\Users\DELL\Documents\GitHub\Authetec-\benchmarks"
repos = ["repo1_lightgbm", "repo2_ensemble", "repo3_pipeline",
         "repo4_insurance", "repo5_graph", "repo6_identity"]
for name in repos:
    path = os.path.join(BASE, name)
    print(f"=== {name} ===")
    # Look for license indicators
    patterns = []
    for root, dirs, files in os.walk(path):
        if ".git" in root: continue
        for f in files:
            lower = f.lower()
            if "license" in lower or "copying" in lower:
                patterns.append(os.path.join(root, f))
    print("  license-ish files:", patterns[:5] if patterns else "NONE")
    # Check README for license badge/text
    for rfile in glob.glob(os.path.join(path, "README*")):
        try:
            content = open(rfile, encoding="utf-8", errors="replace").read()[:3000]
            hits = re.findall(r"(?i)(license[^\n]{0,80}|MIT|Apache|BSD|GPL|AGPL)", content)
            if hits:
                print("  README license hints:", list(dict.fromkeys(hits))[:6])
        except Exception as e:
            print("  read err", e)
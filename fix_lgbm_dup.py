import pathlib
ROOT = pathlib.Path(r"C:\Users\DELL\Documents\GitHub\Authetec-\benchmarks\adapters\lightgbm_fraud_adapter.py")
lines = ROOT.read_text(encoding="utf-8").splitlines()
# Find second occurrence of the module docstring -> truncate there
cut = None
count = 0
for i, line in enumerate(lines):
    if line.startswith('"""LightGBM Fraud Detection Adapter'):
        count += 1
        if count == 2:
            cut = i
            break
if cut is None:
    print("No duplicate found; file OK:", len(lines), "lines")
else:
    # keep lines before cut, but drop trailing blank lines
    kept = lines[:cut]
    while kept and kept[-1].strip() == "":
        kept.pop()
    ROOT.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"Truncated to {cut} lines (removed {len(lines)-cut} stray lines)")
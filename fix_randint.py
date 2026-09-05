import pathlib
sys_encoding = "utf-8"
BASE = pathlib.Path(r"C:\Users\DELL\Documents\GitHub\Authetec-\benchmarks\adapters")
for path in BASE.glob("*.py"):
    text = path.read_text(encoding=sys_encoding)
    if "rng.integers" in text:
        text = text.replace("rng.integers", "rng.randint")
        path.write_text(text, encoding=sys_encoding)
        print(f"Fixed: {path.name}")
print("All fixed.")
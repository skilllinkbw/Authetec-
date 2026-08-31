import ast, sys, glob
sys.stdout.reconfigure(encoding='utf-8')
ok = True
for path in glob.glob("benchmarks/adapters/*.py"):
    try:
        ast.parse(open(path, encoding="utf-8").read())
        print(f"  [OK]   {path}")
    except SyntaxError as e:
        ok = False
        print(f"  [FAIL] {path}: line {e.lineno}: {e.msg}")
print("ALL SYNTAX OK" if ok else "SYNTAX ERRORS FOUND")
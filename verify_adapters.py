"""Verify all adapter imports work."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"C:\Users\DELL\Documents\GitHub\Authetec-")

from benchmarks.adapters import ALL_ADAPTERS
print(f"Registered {len(ALL_ADAPTERS)} adapters:")
for name, cls in ALL_ADAPTERS.items():
    inst = cls()
    meta = inst.metadata()
    print(f"  - {name}: {meta['repo']} ({meta['commit'][:8]})")
    print(f"      license: {meta['license']}")
print("ALL ADAPTER IMPORTS OK")
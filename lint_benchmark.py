import time
import os
import sys
import subprocess
import shutil

vault_path = "/tmp/lint_bench_vault"
if os.path.exists(vault_path):
    shutil.rmtree(vault_path)
os.makedirs(os.path.join(vault_path, "References"), exist_ok=True)
os.makedirs(os.path.join(vault_path, "Ideas"), exist_ok=True)
os.environ["SECOND_BRAIN_VAULT_PATH"] = vault_path

# Create some dummy files
for i in range(1000):
    with open(os.path.join(vault_path, "References", f"ref_{i}.md"), "w") as f:
        f.write(f"---\ntype: reference\ntopic: bench\n---\n# Ref {i}\nBody text for {i}. [[ref_{(i+1)%1000}]]")
    with open(os.path.join(vault_path, "Ideas", f"idea_{i}.md"), "w") as f:
        f.write(f"---\ntype: idea\nstatus: draft\n---\n# Idea {i}\nBody text for {i}. [[ref_{i}]]")

for mode in ["check", "quick"]:
    t0 = time.time()
    subprocess.run([sys.executable, "scripts/lint.py", mode], stdout=subprocess.DEVNULL)
    t1 = time.time()
    print(f"Lint '{mode}' took {t1 - t0:.4f} seconds")

# Benchmark internal loop using caching manually
t0 = time.time()
subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'scripts'); import lint; import pathlib; vault = pathlib.Path('/tmp/lint_bench_vault'); report = lint.run_check(vault, quick=False)"], stdout=subprocess.DEVNULL)
t1 = time.time()
print(f"Lint Internal 'run_check(quick=False)' took {t1 - t0:.4f} seconds")

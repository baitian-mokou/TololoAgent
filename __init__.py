import os, sys
sys.stdout.reconfigure(encoding="utf-8")

txt_dir = r"data\txt"
files = [x for x in os.listdir(txt_dir) if x.endswith(".txt")]

fws = [(x, os.path.getsize(os.path.join(txt_dir, x))) for x in files]
fws.sort(key=lambda x: x[1])

n = len(fws)
step = max(n // 20, 1)
idx = [0] + [i for i in range(step, n, step)] + {n-1]
sel = list(dict.fromkeys([fws[i] for i in idx if i < n]))
sel.sort(key=lambda x: x[1])

print("Total:", n, "Selected:", len(sel))
print()

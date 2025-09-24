import os, subprocess
from ..config import SWMM_EXE

def run_cli(inp_path: str, rpt_path: str = None, out_path: str = None):
    if not rpt_path:
        rpt_path = os.path.splitext(inp_path)[0] + ".rpt"
    if not out_path:
        out_path = os.path.splitext(inp_path)[0] + ".out"
    cmd = [SWMM_EXE, inp_path, rpt_path, out_path]
    subprocess.run(cmd, check=True)
    return {"ok": True, "rpt": rpt_path, "out": out_path}

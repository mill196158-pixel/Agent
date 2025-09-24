import os
from dotenv import load_dotenv
load_dotenv()

ACAD_EXE = os.getenv("ACAD_EXE", r"C:\Program Files\Autodesk\AutoCAD 2024\acad.exe")
SWMM_EXE = os.getenv("SWMM_EXE", r"C:\Program Files (x86)\EPA SWMM 5.2\swmm5.exe")

# тайминги/поведение
TYPE_DELAY = 0.03
STEP_RETRIES = 2

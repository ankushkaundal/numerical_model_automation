@echo on

call C:\ProgramData\miniconda3\Scripts\activate.bat
call conda activate D:\00_GW_Tools\venv

cd /d "F:\cauvery_Update\2026_cauvery_project\GW\Output\cauvery397\heads"

call python DIS_hds_to_asc.py
call python DIS_dH_asc.py

cd /d "..\flows"

call python cs2_final.py
call python calculate_fdc.py
call python fdc_subplots_4by2.py
call conda deactivate
call conda deactivate

pause
import os, zipfile

exclude_dirs = {'.venv', 'package_modules', '.git', '__pycache__'}
base_dir = r"C:\Code\backend"
zip_path = r"C:\Code\backend.zip"

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(base_dir):
        # modify dirs in-place to skip excluded folders
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            filepath = os.path.join(root, file)
            relpath = os.path.relpath(filepath, base_dir)
            zf.write(filepath, relpath)

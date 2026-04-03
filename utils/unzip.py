import zipfile
import io

def extract_zip(content: bytes):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        files = {}
        for name in z.namelist():
            if not name.endswith("/"):  # skip directories
                files[name] = z.read(name).decode("utf-8", errors="ignore")
        return files
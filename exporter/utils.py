import os
import re
import tempfile

def sanitize_filename(title: str) -> str:
    """Keeps unicode, but removes characters problematic on most filesystems."""
    cleaned = re.sub(r'[<>:\"\'/|?*]', '_', title)
    cleaned = cleaned.replace(' ', '_')
    return cleaned

def make_dir(path: str) -> None:
    """Creates a directory if it doesn't exist."""
    os.makedirs(path, exist_ok=True)

def atomic_write_text(dest_path: str, text: str, encoding='utf-8') -> None:
    """Atomically write text to dest_path by writing to a temp file and then replacing."""
    dirpath = os.path.dirname(dest_path) or '.'
    fd, tmp_path = tempfile.mkstemp(prefix='.tmp-', dir=dirpath, text=True)
    os.close(fd)
    try:
        with open(tmp_path, 'w', encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, dest_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

def atomic_write_bytes(dest_path: str, stream_generator) -> None:
    """Atomically write bytes by streaming from a generator to a temp file."""
    dirpath = os.path.dirname(dest_path) or '.'
    fd, tmp_path = tempfile.mkstemp(prefix='.tmp-', dir=dirpath)
    os.close(fd)
    try:
        with open(tmp_path, 'wb') as f:
            for chunk in stream_generator():
                if chunk:
                    f.write(chunk)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, dest_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
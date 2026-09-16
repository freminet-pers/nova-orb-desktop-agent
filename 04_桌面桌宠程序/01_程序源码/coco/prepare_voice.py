"""Explicit one-time model setup: python -m coco.prepare_voice."""
from faster_whisper.utils import download_model
from .voice import MODEL_DIR

if __name__ == '__main__':
    print(download_model('small', output_dir=str(MODEL_DIR)))

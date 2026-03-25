import sys
from pathlib import Path

# Garante que a raiz do projeto está sempre no sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

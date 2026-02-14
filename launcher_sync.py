"""PyInstaller entry point for the sync service."""
from src.sync_service import main
import sys

sys.exit(main())

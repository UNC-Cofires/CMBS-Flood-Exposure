from pathlib import Path
import yaml

def find_project_root(marker=".project_root") -> Path:
    """Walk up the directory tree to find the project root."""
    path = Path(__file__).resolve()
    for parent in [path, *path.parents]:
        if (parent / marker).exists():
            return parent
    raise FileNotFoundError(
        f"Could not find project root. "
        f"Is '{marker}' present at the top level?"
    )

def load_config() -> dict:
    """Load config.yaml from the project root, if it exists."""
    root = find_project_root()
    config_path = root / "config.yaml"
    config = {"project_root": root}  # Always include the root
    if config_path.exists():
        with open(config_path) as f:
            user_config = yaml.safe_load(f)
            config.update(user_config or {})
    return config

# Usage in any script:
# from src.utils.config import find_project_root, load_config
# ROOT = find_project_root()
# config = load_config()

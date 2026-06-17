import sys
import yaml
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config.yaml"
EXAMPLE_PATH = ROOT / "config_example.yaml"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("=" * 60)
        print("  错误：找不到配置文件 config.yaml")
        print()
        print("  请复制配置模板并修改：")
        print(f"    cp {EXAMPLE_PATH} {CONFIG_PATH}")
        print(f"  然后编辑 {CONFIG_PATH} 填入你的配置信息")
        print("=" * 60)
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


config = load_config()

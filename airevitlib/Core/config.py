# airevitlib/core/config.py
import os
import json

class ConfigManager:
    """Handles credentials and configuration parameters saved to git-ignored files."""

    def __init__(self, project_root: str):
        self.config_path = os.path.join(project_root, "airevit_config.json")

    def load_config(self) -> dict:
        config = {
            "api_key": os.environ.get("GEMINI_API_KEY", ""),
            "selected_model": "gemini-2.5-flash"
        }
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                    if data.get("api_key"):
                        config["api_key"] = data["api_key"].strip()
                    if data.get("selected_model"):
                        config["selected_model"] = data["selected_model"].strip()
            except:
                pass
        return config

    def save_config(self, api_key: str, selected_model: str):
        try:
            data = {
                "api_key": api_key.strip(),
                "selected_model": selected_model.strip()
            }
            with open(self.config_path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Failed to cache configuration parameters: {e}")
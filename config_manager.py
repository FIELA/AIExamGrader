# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

import json
import os
from typing import Dict, Any, List

class ConfigManager:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
                self.config = {}
        
        # Ensure profiles structure exists
        if "profiles" not in self.config:
            self.config["profiles"] = {}
        if "last_used" not in self.config:
            self.config["last_used"] = ""

    def save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value
        self.save_config()
    
    # Profile Management Methods
    def get_profile_names(self) -> List[str]:
        """Get list of all saved profile names"""
        return list(self.config.get("profiles", {}).keys())
    
    def save_profile(self, name: str, profile_data: Dict[str, Any]):
        """Save a configuration profile"""
        if "profiles" not in self.config:
            self.config["profiles"] = {}
        self.config["profiles"][name] = profile_data
        self.config["last_used"] = name
        self.save_config()
    
    def load_profile(self, name: str) -> Dict[str, Any]:
        """Load a configuration profile"""
        return self.config.get("profiles", {}).get(name, {})
    
    def delete_profile(self, name: str):
        """Delete a configuration profile"""
        if "profiles" in self.config and name in self.config["profiles"]:
            del self.config["profiles"][name]
            if self.config.get("last_used") == name:
                self.config["last_used"] = ""
            self.save_config()
    
    def get_last_used(self) -> str:
        """Get the name of the last used profile"""
        return self.config.get("last_used", "")

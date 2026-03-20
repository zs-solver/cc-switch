import os
import json
import glob
from urllib.parse import urlparse


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


class ConfigManager:
    """配置全部状态与操作 — 替代原有的全局变量和散落的函数"""

    def __init__(self, script_dir=None):
        # script_dir 指向项目根目录（config.json 所在目录）
        # 默认值：__file__ 的上两级（core/ → 项目根）
        self.script_dir = script_dir or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        self.config_file = os.path.join(self.script_dir, "config.json")
        self.local_settings_dir = os.path.join(self.script_dir, "settings")
        self._load()

    def _load(self):
        """从 config.json 读取配置"""
        with open(self.config_file, "r", encoding="utf-8") as f:
            self._raw = json.load(f)
        self.settings_dir = os.path.expanduser(self._raw["settings_dir"])
        self.settings_file = os.path.join(self.settings_dir, "settings.json")
        self.known_env_keys = set(self._raw["known_env_keys"])
        self._configs = self._raw["configs"]

    @property
    def configs(self) -> list:
        """返回配置列表（直接引用，不做拷贝）"""
        return self._configs

    def save(self):
        """将当前配置回写到 config.json"""
        self._raw["configs"] = self._configs
        write_json(self.config_file, self._raw)

    def find_cfg_path(self, filename) -> str | None:
        """查找配置文件路径，优先项目 settings/ 目录，其次家目录"""
        local_path = os.path.join(self.local_settings_dir, filename)
        if os.path.exists(local_path):
            return local_path
        home_path = os.path.join(self.settings_dir, filename)
        if os.path.exists(home_path):
            return home_path
        return None

    def auto_discover(self) -> list:
        """扫描 settings/ 和 ~/.claude/ 下的 settings-*.json，自动补充未登记的条目并回写"""
        known_filenames = {entry["filename"] for entry in self._configs}
        discovered = []

        for scan_dir in [self.local_settings_dir, self.settings_dir]:
            if not os.path.isdir(scan_dir):
                continue
            for filepath in glob.glob(os.path.join(scan_dir, "settings-*.json")):
                filename = os.path.basename(filepath)
                if filename in known_filenames:
                    continue
                known_filenames.add(filename)
                try:
                    cfg = read_json(filepath)
                    base_url = cfg.get("env", {}).get("ANTHROPIC_BASE_URL", "")
                    entry = {
                        "name": self.derive_name(filename),
                        "filename": filename,
                        "website": self.extract_website(base_url) if base_url else "",
                        "base_url": base_url,
                    }
                    discovered.append(entry)
                except Exception:
                    continue

        if discovered:
            self._configs.extend(discovered)
            self.save()

        return discovered

    def detect_current(self) -> str | None:
        """根据当前 settings.json 的 env 匹配到哪个配置"""
        settings = read_json(self.settings_file)
        cur_url = settings.get("env", {}).get("ANTHROPIC_BASE_URL", "")
        cur_token = settings.get("env", {}).get("ANTHROPIC_AUTH_TOKEN", "")
        for entry in self._configs:
            cfg_path = self.find_cfg_path(entry["filename"])
            if not cfg_path:
                continue
            cfg = read_json(cfg_path)
            cfg_url = cfg.get("env", {}).get("ANTHROPIC_BASE_URL", "")
            cfg_token = cfg.get("env", {}).get("ANTHROPIC_AUTH_TOKEN", "")
            if cur_url == cfg_url and cur_token == cfg_token:
                return entry["name"]
        return None

    def switch(self, filename: str):
        """将目标配置文件的 env 和 model 覆盖到 settings.json，清除多余 env 变量"""
        target_path = self.find_cfg_path(filename)
        if not target_path:
            raise FileNotFoundError(f"找不到配置文件: {filename}")
        target = read_json(target_path)
        current = read_json(self.settings_file)

        # 用目标的 env 完全替换，但只保留已知的 env 键
        new_env = {}
        for k, v in target.get("env", {}).items():
            if k in self.known_env_keys:
                new_env[k] = v
        current["env"] = new_env

        # 覆盖 model（如果目标有 model 字段就覆盖，没有就删除）
        if "model" in target:
            current["model"] = target["model"]
        elif "model" in current:
            del current["model"]

        write_json(self.settings_file, current)

    def add(self, base_url, api_key, name="", model="") -> dict:
        """新增一个配置：生成 settings 文件、追加到 config.json"""
        # 自动推导 name
        if not name:
            parsed = urlparse(base_url)
            name = parsed.hostname or base_url

        # 生成文件名 slug：取域名，替换特殊字符
        parsed = urlparse(base_url)
        slug = (parsed.hostname or "custom").replace(".", "-")
        filename = f"settings-{slug}.json"

        # 避免文件名冲突，加数字后缀
        existing_filenames = {entry["filename"] for entry in self._configs}
        if filename in existing_filenames:
            i = 2
            while f"settings-{slug}-{i}.json" in existing_filenames:
                i += 1
            filename = f"settings-{slug}-{i}.json"

        # 生成 settings 文件内容
        settings_content = {
            "env": {
                "ANTHROPIC_AUTH_TOKEN": api_key,
                "ANTHROPIC_BASE_URL": base_url,
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            }
        }
        if model:
            settings_content["model"] = model

        # 写入 settings/ 目录
        os.makedirs(self.local_settings_dir, exist_ok=True)
        settings_path = os.path.join(self.local_settings_dir, filename)
        write_json(settings_path, settings_content)

        # 追加到配置列表并持久化
        new_entry = {
            "name": name,
            "filename": filename,
            "website": self.extract_website(base_url),
            "base_url": base_url,
        }
        self._configs.append(new_entry)
        self.save()

        return new_entry

    def get_test_list(self) -> list:
        """统一的测试配置列表构建，返回 [(name, base_url, api_key, models, cfg_path), ...]"""
        from core.test_runner import FALLBACK_MODELS

        test_list = []
        for entry in self._configs:
            cfg_path = self.find_cfg_path(entry["filename"])
            if not cfg_path:
                continue
            try:
                cfg = read_json(cfg_path)
                base_url = cfg.get("env", {}).get("ANTHROPIC_BASE_URL", "")
                api_key = cfg.get("env", {}).get("ANTHROPIC_AUTH_TOKEN", "")
                cfg_model = (cfg.get("model")
                             or cfg.get("env", {}).get("ANTHROPIC_MODEL"))
                if cfg_model and cfg_model not in FALLBACK_MODELS:
                    models = [cfg_model]
                else:
                    models = FALLBACK_MODELS
                if base_url and api_key:
                    test_list.append((entry["name"], base_url, api_key, models, cfg_path))
            except Exception:
                continue
        return test_list

    @staticmethod
    def extract_website(base_url) -> str:
        """从 base_url 提取 scheme://host 作为 website"""
        parsed = urlparse(base_url)
        if parsed.scheme and parsed.hostname:
            port = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
            return f"{parsed.scheme}://{parsed.hostname}{port}"
        return base_url

    @staticmethod
    def derive_name(filename) -> str:
        """从文件名推导显示名称: settings-foo-bar.json -> foo-bar"""
        name = filename
        if name.startswith("settings-"):
            name = name[len("settings-"):]
        if name.endswith(".json"):
            name = name[:-len(".json")]
        return name or filename

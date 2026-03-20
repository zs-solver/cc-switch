import sys
import os
import json
import time
import subprocess
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# 每个配置尝试的路径列表
API_PATHS = ["/v1/messages", "/messages"]
# 无明确模型时尝试的模型列表
FALLBACK_MODELS = ["claude-opus-4-6-thinking", "claude-opus-4-6", "opus"]


def _test_url(url, headers, body):
    """对指定 URL 发送流式请求，返回指标字典，失败则抛异常"""
    t_start = time.time()
    t_first = None
    text = ""

    resp = requests.post(url, headers=headers, json=body,
                         stream=True, timeout=30)
    resp.raise_for_status()

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            break
        try:
            data = json.loads(data_str)
        except Exception:
            continue
        if data.get("type") == "content_block_delta":
            if t_first is None:
                t_first = time.time()
            text += data.get("delta", {}).get("text", "")

    t_end = time.time()
    if t_first is None or not text:
        raise ValueError("无响应内容")

    ttft = t_first - t_start
    total = t_end - t_start
    length = len(text)
    speed = length / total if total > 0 else 0
    return {
        "ttft": f"{ttft:.2f}s",
        "length": str(length),
        "total": f"{total:.2f}s",
        "speed": f"{speed:.1f} 字/秒",
        "response": text,
    }


def test_single_config(name, base_url, api_key, models):
    """同时测试多条路径 × 多个模型，返回首个成功的结果"""
    base = base_url.rstrip("/")
    headers = {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    result = {"name": name, "status": "❌", "ttft": "-", "length": "-",
              "total": "-", "speed": "-", "response": "",
              "path": "-", "model": "-"}

    combos = [(m, p) for m in models for p in API_PATHS]

    def try_combo(model, path):
        body = {
            "model": model,
            "max_tokens": 200,
            "stream": True,
            "messages": [{"role": "user", "content": "Hi"}],
        }
        r = _test_url(base + path, headers, body)
        r["path"] = path
        r["model"] = model
        return r

    with ThreadPoolExecutor(max_workers=len(combos)) as pool:
        futures = {pool.submit(try_combo, m, p): f"{m} {p}"
                   for m, p in combos}
        errors = []
        for future in as_completed(futures):
            label = futures[future]
            try:
                r = future.result()
                result.update(r)
                result["status"] = "✅"
                return result
            except Exception as e:
                errors.append(f"{label}: {e}")

    result["response"] = " | ".join(errors)
    return result


def test_single_config_cli(name, settings_path):
    """通过 claude --settings <path> -p "Hi" 测试配置"""
    result = {"name": name, "cli_status": "❌", "cli_total": "-",
              "cli_response": ""}
    t_start = time.time()
    try:
        proc = subprocess.run(
            ["claude", "--settings", settings_path, "-p", "Hi"],
            capture_output=True, text=True, timeout=120,
            shell=True, encoding="utf-8", errors="replace",
        )
        total = time.time() - t_start
        result["cli_total"] = f"{total:.2f}s"
        output = proc.stdout.strip()
        if proc.returncode == 0 and output:
            result["cli_status"] = "✅"
            result["cli_response"] = output
        else:
            result["cli_response"] = proc.stderr.strip() or "无输出"
    except subprocess.TimeoutExpired:
        result["cli_total"] = f"{time.time() - t_start:.2f}s"
        result["cli_response"] = "超时(120s)"
    except Exception as e:
        result["cli_total"] = f"{time.time() - t_start:.2f}s"
        result["cli_response"] = str(e)
    return result


# --------------- CLI 模式 ---------------

if __name__ == "__main__":
    # 将项目根目录加入 sys.path，解决包内直接运行的导入问题
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from core.config_manager import ConfigManager

    cm = ConfigManager(script_dir=project_root)
    configs = cm.get_test_list()

    if not configs:
        print("未找到可测试的配置")
        sys.exit(1)

    print(f"开始测试 {len(configs)} 个配置 (HTTP + CLI)...\n")

    # 并发跑 HTTP 测试
    http_results = {}
    with ThreadPoolExecutor(max_workers=len(configs)) as pool:
        futures = {
            pool.submit(test_single_config, c[0], c[1], c[2], c[3]): c[0]
            for c in configs
        }
        for future in as_completed(futures):
            name = futures[future]
            http_results[name] = future.result()

    # 并发跑 CLI 测试
    cli_results = {}
    with ThreadPoolExecutor(max_workers=min(len(configs), 4)) as pool:
        futures = {
            pool.submit(test_single_config_cli, c[0], c[4]): c[0]
            for c in configs
        }
        for future in as_completed(futures):
            name = futures[future]
            cli_results[name] = future.result()

    # 按原始顺序输出
    for c in configs:
        name = c[0]
        h = http_results[name]
        cl = cli_results[name]
        print(f"{'='*60}")
        print(f"  {name}")
        print(f"  [HTTP] {h['status']}  模型: {h.get('model','-')}  路径: {h.get('path','-')}")
        print(f"         首字: {h['ttft']}  字数: {h['length']}  总耗时: {h['total']}  速度: {h['speed']}")
        print(f"         响应: {h['response'][:80]}")
        print(f"  [CLI]  {cl['cli_status']}  耗时: {cl['cli_total']}")
        print(f"         响应: {cl['cli_response'][:80]}")

    print(f"{'='*60}")
    print("测试完成")

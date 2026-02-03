import os
import json
import requests
import urllib3
import concurrent.futures
from tqdm import tqdm

# ================= ⚙️ 配置区域 =================
BASE_RES_URL = "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/"
SETTINGS_URL = BASE_RES_URL + "src/settings.4229e.json"
DOWNLOAD_ROOT = "configs" 
MAX_WORKERS = 16 

HEADERS = {
    "Host": "game.sweet-home-maid.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/index.html",
}
# ===============================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_settings_locally():
    """ 优先读取本地 settings 文件，不存在则下载保存 """
    filename = os.path.basename(SETTINGS_URL)
    
    # 1. 尝试读取本地
    if os.path.exists(filename):
        print(f"[-] 📄 发现本地 Settings ({filename})，直接读取...")
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] 本地 Settings 读取失败，尝试重新下载: {e}")

    # 2. 下载并保存
    print(f"[-] ☁️ 正在下载 Settings...")
    try:
        resp = requests.get(SETTINGS_URL, headers=HEADERS, verify=False, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            # 保存到本地
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            print(f"[-] ✅ Settings 已保存至本地: {filename}")
            return data
        else:
            print(f"[X] Settings 下载失败 Status: {resp.status_code}")
            return None
    except Exception as e:
        print(f"[X] Settings 网络请求错误: {e}")
        return None

def download_config_file(args):
    bundle_name, bundle_ver = args
    save_dir = os.path.join(DOWNLOAD_ROOT, bundle_name)
    os.makedirs(save_dir, exist_ok=True)
    
    filename = f"config.{bundle_ver}.json"
    save_path = os.path.join(save_dir, filename)
    
    # [核心修改] 断点续传：如果文件存在且有内容，直接跳过
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        return True # 已存在，视为成功

    url = f"{BASE_RES_URL}assets/{bundle_name}/{filename}"
    
    try:
        resp = requests.get(url, headers=HEADERS, verify=False, timeout=10)
        if resp.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(resp.content)
            return True
        else:
            return False
    except Exception as e:
        # print(f"Error downloading {bundle_name}: {e}")
        return False

def main():
    print("=== DMM Config 文件抓取器 (本地缓存版) ===")
    
    settings = get_settings_locally()
    if not settings:
        return

    try:
        bundle_vers = settings.get('assets', {}).get('bundleVers', {})
        if not bundle_vers:
            print("[X] 未找到 bundleVers 信息")
            return
        print(f"[-] 扫描到 {len(bundle_vers)} 个 Bundle")
    except Exception as e:
        print(f"[X] 解析失败: {e}")
        return

    tasks = []
    for b_name, b_ver in bundle_vers.items():
        tasks.append((b_name, b_ver))

    print(f"[-] 开始处理 Config (已存在的会自动跳过)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 使用 list() 触发迭代以显示进度条
        list(tqdm(executor.map(download_config_file, tasks), total=len(tasks), unit="file"))

    print(f"\n✅ 全部完成！Config 文件保存在: {os.path.abspath(DOWNLOAD_ROOT)}")

if __name__ == "__main__":
    main()
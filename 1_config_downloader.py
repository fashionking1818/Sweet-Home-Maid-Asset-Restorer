import os
import requests
import urllib3
import concurrent.futures
from tqdm import tqdm

# ================= ⚙️ 配置区域 =================
BASE_RES_URL = "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/"
SETTINGS_URL = BASE_RES_URL + "src/settings.4229e.json"
DOWNLOAD_ROOT = "configs" # 修改了保存目录名称，避免混淆，你可以改回 "assets"
MAX_WORKERS = 16 # 下载小文本文件可以开大一点并发

HEADERS = {
    "Host": "game.sweet-home-maid.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/index.html",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin"
}
# ===============================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def download_config_file(args):
    """
    仅下载 Config 文件并保存到对应目录
    结构: {DOWNLOAD_ROOT}/{bundle_name}/config.{bundle_ver}.json
    """
    bundle_name, bundle_ver = args
    
    # 1. 构造目标路径
    # 例如: assets_configs/Chara
    save_dir = os.path.join(DOWNLOAD_ROOT, bundle_name)
    os.makedirs(save_dir, exist_ok=True)
    
    # 2. 构造文件名和 URL
    # 例如: config.f97fc.json
    filename = f"config.{bundle_ver}.json"
    save_path = os.path.join(save_dir, filename)
    
    url = f"{BASE_RES_URL}assets/{bundle_name}/{filename}"
    
    # 3. 下载逻辑
    try:
        # 如果文件已存在且大小不为0，跳过
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return True

        resp = requests.get(url, headers=HEADERS, verify=False, timeout=10)
        if resp.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(resp.content)
            return True
        else:
            # 某些 Bundle (如 internal, resources) 放在不同的位置，这里仅针对 assets 下的 bundle
            # 如果 404 可以忽略
            return False
    except Exception as e:
        print(f"Error downloading {bundle_name}: {e}")
        return False

def main():
    print("=== DMM Config 文件抓取器 ===")
    print(f"[-] 保存位置: {os.path.abspath(DOWNLOAD_ROOT)}")
    
    # 1. 获取全局 Settings
    try:
        print(f"[*] 正在获取 Settings: {SETTINGS_URL}")
        settings_resp = requests.get(SETTINGS_URL, headers=HEADERS, verify=False)
        if settings_resp.status_code != 200:
            print(f"[X] 获取 Settings 失败，状态码: {settings_resp.status_code}")
            return
        settings = settings_resp.json()
        
        # 提取所有 Bundle 的版本信息
        # 结构: {'Chara': 'f97fc', 'System': 'a1b2c', ...}
        bundle_vers = settings.get('assets', {}).get('bundleVers', {})
        
        if not bundle_vers:
            print("[X] 未找到 bundleVers 信息")
            return
            
        print(f"[-] 扫描到 {len(bundle_vers)} 个 Bundle，准备下载 Config...")
        
    except Exception as e:
        print(f"[X] Settings 解析失败: {e}")
        return

    # 2. 准备任务列表
    tasks = []
    for b_name, b_ver in bundle_vers.items():
        tasks.append((b_name, b_ver))

    # 3. 并发下载
    # 使用 tqdm 显示进度
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(tqdm(executor.map(download_config_file, tasks), total=len(tasks), unit="file"))

    print(f"\n✅ 全部完成！Config 文件已保存在 {DOWNLOAD_ROOT} 目录下。")

if __name__ == "__main__":
    main()
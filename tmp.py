import os
import requests
import json
import base64
import binascii
import urllib3
import time
from concurrent.futures import ThreadPoolExecutor
import threading

# ================= 🔧 配置区域 =================
BASE_RES_URL = "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/"
# 确保这是最新的 Settings URL
SETTINGS_URL = BASE_RES_URL + "src/settings.4229e.json"

TARGET_BUNDLES = ["GardenCommon"] 
SAVE_DIR = "Raw_Assets_Binary" # 名字改一下，表示这里面可能是二进制文件

HEADERS = {
    "Host": "game.sweet-home-maid.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/index.html",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin"
}
# ===============================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
print_lock = threading.Lock()

def decompress_uuid(uuid_str):
    """
    【核心修正】
    必须把 Cocos 的 22位 短码还原成 36位 标准 UUID
    因为服务器上的文件夹和文件名都是用的 36位 UUID！
    """
    if len(uuid_str) == 36: return uuid_str
    if len(uuid_str) != 22 and len(uuid_str) != 23: return uuid_str
    
    # 移除可能存在的下划线前缀或后缀处理
    temp_uuid = uuid_str[1:] if uuid_str.startswith('_') else uuid_str
    
    try:
        b64 = temp_uuid[2:].replace('-', '+').replace('_', '/')
        pad = len(b64) % 4
        if pad > 0: b64 += '=' * (4 - pad)
        data = base64.b64decode(b64)
        hex_s = binascii.hexlify(data).decode('utf-8')
        prefix = temp_uuid[:2]
        return f"{prefix}{hex_s[0:6]}-{hex_s[6:10]}-{hex_s[10:14]}-{hex_s[14:18]}-{hex_s[18:]}"
    except:
        return uuid_str

def decode_versions(uuids, version_array):
    v_map = {}
    if not version_array: return v_map
    for i in range(0, len(version_array), 2):
        idx = version_array[i]
        ver = version_array[i+1]
        if idx < len(uuids):
            v_map[uuids[idx]] = ver
    return v_map

def try_download(url, save_path):
    try:
        resp = requests.get(url, headers=HEADERS, verify=False, timeout=10)
        if resp.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(resp.content)
            return True, resp.status_code
        return False, resp.status_code
    except Exception as e:
        return False, str(e)

def process_file_task(args):
    raw_uuid, ver, bundle_name, bundle_save_dir, counter, total = args
    
    # 1. 还原长 UUID (关键步骤)
    long_uuid = decompress_uuid(raw_uuid)
    
    # 2. 确定文件夹前缀 (使用长 UUID 的前两位)
    # 你的日志显示: /import/d8/d8933... -> 前缀是 d8
    folder_prefix = long_uuid[:2]
    
    # 3. 构造基础路径
    base_url_path = f"{BASE_RES_URL}assets/{bundle_name}/import/{folder_prefix}/{long_uuid}.{ver}"
    
    # 4. 尝试下载策略
    # 优先尝试 .cconb (根据你的最新线索)
    # 其次尝试 .json (传统格式)
    
    success = False
    
    # --- 尝试 1: .cconb ---
    url_cconb = base_url_path + ".cconb"
    path_cconb = os.path.join(bundle_save_dir, f"{long_uuid}.cconb")
    
    ok, code = try_download(url_cconb, path_cconb)
    if ok:
        success = True
        # with print_lock: print(f"    [+] 下载 CCONB: {long_uuid}")
    else:
        # --- 尝试 2: .json ---
        url_json = base_url_path + ".json"
        path_json = os.path.join(bundle_save_dir, f"{long_uuid}.json")
        ok_json, code_json = try_download(url_json, path_json)
        if ok_json:
            success = True
            # with print_lock: print(f"    [+] 下载 JSON: {long_uuid}")

    # 进度条
    with print_lock:
        counter[0] += 1
        if counter[0] % 10 == 0 or counter[0] == total:
            print(f"\r    ⏳ 进度: {counter[0]}/{total} ...", end="")
            
    # 如果两次都失败且状态码是 403/404，可能需要记录一下(用于后续分析)
    # 但为了脚本不中断，这里暂不抛出错误

def main():
    print(f"=== DMM 资源下载器 (.cconb 适配版) ===")
    
    try:
        settings = requests.get(SETTINGS_URL, headers=HEADERS, verify=False, timeout=10).json()
        bundle_vers = settings.get('assets', {}).get('bundleVers', {})
    except Exception as e:
        print(f"[X] Settings 获取失败: {e}")
        return

    for bundle_name in TARGET_BUNDLES:
        print(f"\n\n📁 处理包: {bundle_name}")
        bundle_hash = bundle_vers.get(bundle_name)
        if not bundle_hash:
            print(f"    [!] 包名未找到")
            continue

        try:
            config_url = f"{BASE_RES_URL}assets/{bundle_name}/config.{bundle_hash}.json"
            config = requests.get(config_url, headers=HEADERS, verify=False, timeout=10).json()
        except:
            print(f"    [X] Config 下载失败")
            continue

        uuids = config.get('uuids', [])
        import_map = decode_versions(uuids, config.get('versions', {}).get('import', []))
        
        safe_name = bundle_name.replace("assets/", "").replace("/", "_")
        bundle_save_dir = os.path.join(SAVE_DIR, safe_name)
        os.makedirs(bundle_save_dir, exist_ok=True)
        
        total = len(import_map)
        print(f"    [-] 队列长度: {total}，尝试 .cconb 和 .json 下载...")
        
        tasks = []
        counter = [0]
        
        for raw_uuid, ver in import_map.items():
            tasks.append((raw_uuid, ver, bundle_name, bundle_save_dir, counter, total))
            
        with ThreadPoolExecutor(max_workers=32) as executor:
            executor.map(process_file_task, tasks)

    print(f"\n\n✅ 任务结束。")
    print(f"请检查 '{SAVE_DIR}' 文件夹。")
    print("注意：下载下来的可能是 .cconb 文件，这是一种二进制格式，后续需要反序列化才能看到里面的 Spine 数据。")
    print("先确认文件是否有内容（大小 > 0KB）。")

if __name__ == "__main__":
    main()
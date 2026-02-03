import os
import json
import requests
import base64
import binascii
import urllib3
import concurrent.futures
from tqdm import tqdm

# ================= ⚙️ 配置区域 =================
LOCAL_CONFIG_DIR = "configs" 
SAVE_IMPORT_ROOT = "imports" 
BASE_RES_URL = "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/"
SETTINGS_URL = BASE_RES_URL + "src/settings.4229e.json" # 这里为了解析本地settings文件名需要保留URL
MAX_WORKERS = 16

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/index.html",
}
# ===============================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
EXISTING_UUIDS = set()

def get_settings_filename():
    return os.path.basename(SETTINGS_URL)

def decompress_uuid(uuid_str):
    suffix = ""
    base_uuid = uuid_str
    if "@" in uuid_str:
        parts = uuid_str.split("@", 1)
        base_uuid = parts[0]
        suffix = "@" + parts[1]

    real_base = base_uuid
    if len(base_uuid) == 22 or len(base_uuid) == 23:
        temp_uuid = base_uuid[1:] if base_uuid.startswith('_') else base_uuid
        try:
            b64 = temp_uuid[2:].replace('-', '+').replace('_', '/')
            pad = len(b64) % 4
            if pad > 0: b64 += '=' * (4 - pad)
            data = base64.b64decode(b64)
            hex_s = binascii.hexlify(data).decode('utf-8')
            prefix = temp_uuid[:2]
            real_base = f"{prefix}{hex_s[0:6]}-{hex_s[6:10]}-{hex_s[10:14]}-{hex_s[14:18]}-{hex_s[18:]}"
        except:
            pass
    return real_base + suffix

def scan_local_files():
    """ 建立本地文件索引，实现极速跳过 """
    print(f"[-] 正在索引本地文件: {os.path.abspath(SAVE_IMPORT_ROOT)}")
    count = 0
    if not os.path.exists(SAVE_IMPORT_ROOT):
        return
        
    for root, dirs, files in os.walk(SAVE_IMPORT_ROOT):
        for file in files:
            if file.endswith(".json"):
                try:
                    name_part = file.replace(".json", "")
                    if "." in name_part:
                        candidate_uuid = name_part.rsplit(".", 1)[0]
                        EXISTING_UUIDS.add(candidate_uuid)
                    EXISTING_UUIDS.add(name_part)
                    count += 1
                except:
                    pass
    print(f"[-] 索引完成！本地已有 {count} 个文件。")

def download_file(url, path):
    # [核心修改] 双重检查：如果物理文件存在，坚决不下载
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        resp = requests.get(url, headers=HEADERS, verify=False, timeout=10)
        if resp.status_code == 200:
            with open(path, 'wb') as f:
                f.write(resp.content)
            return True
        return False
    except:
        return False

def worker_task(args):
    bundle_name, compressed_uuid, import_ver = args
    import_prefix = compressed_uuid[:2]
    real_uuid = decompress_uuid(compressed_uuid)

    # 1. 索引检查 (内存级跳过)
    if real_uuid in EXISTING_UUIDS: return
    if compressed_uuid in EXISTING_UUIDS: return
        
    # 2. 物理路径检查 (磁盘级跳过，针对长UUID路径)
    rel_path_long = f"{bundle_name}/import/{import_prefix}/{real_uuid}.{import_ver}.json"
    save_path_long = os.path.join(SAVE_IMPORT_ROOT, rel_path_long)
    if os.path.exists(save_path_long) and os.path.getsize(save_path_long) > 0:
        return

    # 下载
    url_long = f"{BASE_RES_URL}assets/{rel_path_long}"
    if download_file(url_long, save_path_long):
        return

    # 尝试短UUID
    rel_path_short = f"{bundle_name}/import/{import_prefix}/{compressed_uuid}.{import_ver}.json"
    save_path_short = os.path.join(SAVE_IMPORT_ROOT, rel_path_short)
    url_short = f"{BASE_RES_URL}assets/{rel_path_short}"
    download_file(url_short, save_path_short)

def parse_version_array(uuids, ver_array):
    v_map = {}
    if not ver_array: return v_map
    for i in range(0, len(ver_array), 2):
        idx = ver_array[i]
        ver = ver_array[i+1]
        if idx < len(uuids):
            v_map[uuids[idx]] = ver
    return v_map

def main():
    print("=== DMM Import 智能补全下载器 (Pre-Scan Mode) ===")
    
    # 0. 检查 Settings (仅为了确认连接性或后续扩展，本脚本主要依赖 Config)
    local_settings = get_settings_filename()
    if not os.path.exists(local_settings):
        print(f"[!] 提示：未找到本地 {local_settings}，建议先运行脚本 1 获取最新配置。")
    
    scan_local_files()

    if not os.path.exists(LOCAL_CONFIG_DIR):
        print(f"❌ 找不到配置目录 {LOCAL_CONFIG_DIR}")
        return

    print("[-] 正在解析任务列表...")
    config_files = []
    for root, dirs, files in os.walk(LOCAL_CONFIG_DIR):
        for f in files:
            if f.startswith("config.") and f.endswith(".json"):
                config_files.append(os.path.join(root, f))
    
    tasks = []
    skipped_count = 0
    
    for cfg_path in tqdm(config_files, unit="cfg"):
        try:
            bundle_name = os.path.basename(os.path.dirname(cfg_path))
            with open(cfg_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            uuids = data.get('uuids', [])
            import_vers = parse_version_array(uuids, data.get('versions', {}).get('import', []))
            
            for uuid, ver in import_vers.items():
                real = decompress_uuid(uuid)
                # 检查索引
                if (real in EXISTING_UUIDS) or (uuid in EXISTING_UUIDS):
                    skipped_count += 1
                else:
                    tasks.append((bundle_name, uuid, ver))
        except:
            pass

    print(f"\n✅ 统计结果：本地已有 {skipped_count}，需要下载 {len(tasks)}")

    if not tasks:
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(tqdm(executor.map(worker_task, tasks), total=len(tasks), unit="file"))

    print("\n✅ 补全完成！")

if __name__ == "__main__":
    main()
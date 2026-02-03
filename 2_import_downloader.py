import os
import json
import requests
import base64
import binascii
import urllib3
import concurrent.futures
from tqdm import tqdm
import threading

# ================= ⚙️ 配置区域 =================
LOCAL_CONFIG_DIR = "configs" 
SAVE_IMPORT_ROOT = "imports"  # 确保这个名字和你截图里的文件夹名字一模一样

BASE_RES_URL = "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/"
MAX_WORKERS = 8  # 纯文本下载，开大一点没问题

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/index.html",
}
# ===============================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 全局变量：用于存储本地已有的 UUID ---
EXISTING_UUIDS = set()

def decompress_uuid(uuid_str):
    """ Cocos UUID 解压逻辑 """
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

def compress_uuid(uuid_str):
    """ 简单的压缩逻辑，用于辅助比对（如果需要） """
    # 这里只做简单的返回，主要依靠 decompress 统一比对
    return uuid_str

def scan_local_files():
    """
    核心功能：扫描硬盘，建立已存在文件的索引
    """
    print(f"[-] 正在扫描本地文件: {os.path.abspath(SAVE_IMPORT_ROOT)}")
    count = 0
    if not os.path.exists(SAVE_IMPORT_ROOT):
        return
        
    for root, dirs, files in os.walk(SAVE_IMPORT_ROOT):
        for file in files:
            if file.endswith(".json"):
                # 文件名通常是: uuid.ver.json 或 uuid.json
                # 我们取第一个点之前的部分作为 Key
                # 例如: "0a1b2c3d-....f9941.json" -> "0a1b2c3d-..."
                try:
                    # 假设文件名格式为 UUID.HASH.json，取 UUID 部分
                    # 注意：有些 UUID 本身包含 '-'，所以不能简单用 split
                    # 最稳妥的方法：去掉最后的 .json，再去掉 .ver (如果存在)
                    name_part = file.replace(".json", "")
                    
                    # 尝试分离版本号（通常 UUID 和版本号中间有点）
                    # 如果 UUID 是 36 位 (长) 或 22 位 (短)，我们可以尝试提取
                    if "." in name_part:
                        # 假设最后一段是版本号
                        candidate_uuid = name_part.rsplit(".", 1)[0]
                        EXISTING_UUIDS.add(candidate_uuid)
                    
                    # 同时也把整个文件名（不含json）加进去，以防万一
                    EXISTING_UUIDS.add(name_part)
                    count += 1
                except:
                    pass
    
    print(f"[-] 索引建立完成！本地共有 {count} 个文件 (含变体)。")

def download_file(url, path):
    try:
        # 最后一道防线：检查文件是否存在
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return True

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

    # ============================================
    # ⚡ 极速跳过逻辑
    # ============================================
    # 只要 本地索引里有 这个 UUID (不管是长还是短)，直接跳过
    if real_uuid in EXISTING_UUIDS:
        return
    if compressed_uuid in EXISTING_UUIDS:
        return
        
    # 如果索引没命中，再检查一遍具体路径（双保险）
    rel_path_long = f"{bundle_name}/import/{import_prefix}/{real_uuid}.{import_ver}.json"
    save_path_long = os.path.join(SAVE_IMPORT_ROOT, rel_path_long)
    if os.path.exists(save_path_long):
        return

    # ============================================
    # ⬇️ 下载逻辑
    # ============================================
    # 优先下载 长 UUID 格式
    url_long = f"{BASE_RES_URL}assets/{rel_path_long}"
    if download_file(url_long, save_path_long):
        return

    # 失败则尝试 短 UUID 格式
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
    
    # 1. 先扫描本地已有什么
    scan_local_files()

    if not os.path.exists(LOCAL_CONFIG_DIR):
        print(f"❌ 找不到配置目录 {LOCAL_CONFIG_DIR}")
        return

    # 2. 解析任务列表
    print("[-] 正在解析 Config 生成任务列表...")
    config_files = []
    for root, dirs, files in os.walk(LOCAL_CONFIG_DIR):
        for f in files:
            if f.startswith("config.") and f.endswith(".json"):
                config_files.append(os.path.join(root, f))
    
    tasks = []
    skipped_count = 0
    
    # 预处理：只把【不在】EXISTING_UUIDS 里的任务加入队列
    # 这样进度条就只显示“真正需要下载”的数量
    for cfg_path in tqdm(config_files, unit="cfg"):
        try:
            bundle_name = os.path.basename(os.path.dirname(cfg_path))
            with open(cfg_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            uuids = data.get('uuids', [])
            import_vers = parse_version_array(uuids, data.get('versions', {}).get('import', []))
            
            for uuid, ver in import_vers.items():
                real = decompress_uuid(uuid)
                # 在生成任务阶段直接过滤
                if (real in EXISTING_UUIDS) or (uuid in EXISTING_UUIDS):
                    skipped_count += 1
                else:
                    tasks.append((bundle_name, uuid, ver))
                
        except Exception:
            pass

    print(f"\n✅ 统计结果：")
    print(f"   - 本地已存在 (跳过): {skipped_count}")
    print(f"   - 需要新下载:       {len(tasks)}")

    if not tasks:
        print("🎉 所有文件都已存在，无需下载！")
        return

    print("[-] 开始下载缺失文件...")
    
    # 3. 执行下载 (只下载缺失的)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(tqdm(executor.map(worker_task, tasks), total=len(tasks), unit="file"))

    print("\n✅ 补全完成！")

if __name__ == "__main__":
    main()
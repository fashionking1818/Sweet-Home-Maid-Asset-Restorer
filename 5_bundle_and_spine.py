import os
import requests
import json
import base64
import binascii
import urllib3
import concurrent.futures
import time
from tqdm import tqdm

# ================= ⚙️ 配置区域 =================
BASE_RES_URL = "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/"
SETTINGS_URL = BASE_RES_URL + "src/settings.4229e.json"
DOWNLOAD_ROOT = "assets_restored" 
LOCAL_IMPORT_ROOT = "imports"  
OVERWRITE = False
MAX_WORKERS = 8  # 可以根据网速调高

# 指定下载目标，为空则处理 settings 中的所有 bundle
TARGET_BUNDLES = ['Castcast009001'] 

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/index.html",
}
# ===============================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- [基础工具函数] 100% 还原 3_bundle_downloader 逻辑 ---

def get_settings_locally():
    filename = os.path.basename(SETTINGS_URL)
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    try:
        resp = requests.get(SETTINGS_URL, headers=HEADERS, verify=False)
        data = resp.json()
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        return data
    except: return None

def decompress_uuid(uuid_str):
    if len(uuid_str) == 36: return uuid_str
    if len(uuid_str) != 22 and len(uuid_str) != 23: return uuid_str
    temp_uuid = uuid_str[1:] if uuid_str.startswith('_') else uuid_str
    try:
        b64 = temp_uuid[2:].replace('-', '+').replace('_', '/')
        pad = len(b64) % 4
        if pad > 0: b64 += '=' * (4 - pad)
        data = base64.b64decode(b64)
        hex_s = binascii.hexlify(data).decode('utf-8')
        prefix = temp_uuid[:2]
        return f"{prefix}{hex_s[0:6]}-{hex_s[6:10]}-{hex_s[10:14]}-{hex_s[14:18]}-{hex_s[18:]}"
    except: return uuid_str

def decode_versions(uuids, version_array):
    v_map = {}
    if not version_array: return v_map
    for i in range(0, len(version_array), 2):
        idx = version_array[i]
        ver = version_array[i+1]
        if idx < len(uuids): v_map[uuids[idx]] = ver
    return v_map

def get_extension_by_type(resource_type):
    if not resource_type: return None
    mapping = {
        "cc.ImageAsset": ".png", "cc.Texture2D": ".png", "cc.SpriteFrame": ".png",
        "sp.SkeletonData": ".bin", "cc.AudioClip": ".mp3", "cc.JsonAsset": ".json",
        "cc.TTFFont": ".ttf", "cc.ParticleAsset": ".plist", "cc.TextAsset": ".txt"
    }
    return mapping.get(resource_type)

def parse_import_data_in_memory(json_data):
    try:
        native_ext = None
        if isinstance(json_data, list) and len(json_data) >= 6:
            fields = json_data[3][0][1]
            values = json_data[5][0]
            if "_native" in fields:
                native_ext = values[fields.index("_native") + 1]
        elif isinstance(json_data, dict):
            native_ext = json_data.get("_native")
        return native_ext
    except: return None

# --- [下载核心] 100% 还原 3_bundle_downloader 的后缀尝试逻辑 ---

def download_native_file(url, path):
    if not OVERWRITE and os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        resp = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        if resp.status_code == 200:
            with open(path, 'wb') as f: f.write(resp.content)
            return True
    except: pass
    return False

def process_asset_task(args):
    bundle_name, compressed_uuid, native_hash, import_hash, save_dir, path_info, known_type = args
    real_uuid = decompress_uuid(compressed_uuid)
    
    # 尝试各种可能的后缀，包括用户提到的 .atlas
    exts_to_try = []
    
    # 1. 来自 config 的推荐
    cfg_ext = get_extension_by_type(known_type)
    if cfg_ext: exts_to_try.append(cfg_ext)
    
    # 2. 来自 Import 文件的内部定义 (解析本地 imports 文件夹)
    local_import_rel = f"{bundle_name}/import/{compressed_uuid[:2]}/{real_uuid}.{import_hash}.json"
    local_path = os.path.join(LOCAL_IMPORT_ROOT, local_import_rel)
    if os.path.exists(local_path):
        try:
            with open(local_path, 'r', encoding='utf-8') as f:
                ext_from_imp = parse_import_data_in_memory(json.load(f))
                if ext_from_imp and ext_from_imp not in exts_to_try: exts_to_try.append(ext_from_imp)
        except: pass

    # 3. 兜底枚举 (确保 .atlas, .bin 等不被漏掉)
    for g in [".png", ".jpg", ".bin", ".atlas", ".txt", ".mp3", ".json", ".plist", ".ttf"]:
        if g not in exts_to_try: exts_to_try.append(g)

    real_name = path_info if path_info else real_uuid
    native_base_url = f"{BASE_RES_URL}assets/{bundle_name}/native/{real_uuid[:2]}/{real_uuid}.{native_hash}"
    
    for ext in exts_to_try:
        if download_native_file(f"{native_base_url}{ext}", os.path.join(save_dir, f"{real_name}{ext}")):
            return True
    return False

# --- [Spine 提取工具] 递归寻找骨骼数据 ---

def recursive_find_skeleton(d):
    if isinstance(d, dict):
        if "skeleton" in d and "bones" in d: return d
        for v in d.values():
            res = recursive_find_skeleton(v)
            if res: return res
    elif isinstance(d, list):
        for item in d:
            res = recursive_find_skeleton(item)
            if res: return res
    return None

def extract_spines_for_bundle(bundle_name, config, save_dir):
    types = config.get("types", [])
    if "sp.SkeletonData" not in types: return
    
    spine_idx = types.index("sp.SkeletonData")
    uuids = config.get("uuids", [])
    paths = config.get("paths", {})
    import_vers = decode_versions(uuids, config.get("versions", {}).get("import", []))

    for str_idx, info in paths.items():
        if len(info) > 1 and info[1] == spine_idx:
            idx = int(str_idx)
            u = uuids[idx]
            i_hash = import_vers.get(u)
            if not i_hash: continue
            
            real_u = decompress_uuid(u)
            local_json = os.path.join(LOCAL_IMPORT_ROOT, bundle_name, "import", u[:2], f"{real_u}.{i_hash}.json")
            
            if os.path.exists(local_json):
                try:
                    with open(local_json, 'r', encoding='utf-8') as f:
                        skel = recursive_find_skeleton(json.load(f))
                        if skel:
                            out_path = os.path.join(save_dir, f"{info[0].replace('/', '_')}.json")
                            with open(out_path, 'w', encoding='utf-8') as f_out:
                                json.dump(skel, f_out, indent=2, ensure_ascii=False)
                except: pass

# --- [主流程] Bundle 遍历与子进度条 ---

def process_bundle(bundle_name, bundle_ver, pbar_main):
    if TARGET_BUNDLES and bundle_name not in TARGET_BUNDLES:
        pbar_main.update(1)
        return

    save_dir = os.path.join(DOWNLOAD_ROOT, bundle_name)
    os.makedirs(save_dir, exist_ok=True)
    
    # 获取 Config
    try:
        resp = requests.get(f"{BASE_RES_URL}assets/{bundle_name}/config.{bundle_ver}.json", timeout=10)
        config = resp.json()
    except:
        pbar_main.update(1)
        return

    uuids = config.get('uuids', [])
    paths = config.get('paths', {})
    types = config.get('types', [])
    import_map = decode_versions(uuids, config.get('versions', {}).get('import', []))
    native_ver_arr = config.get('versions', {}).get('native', [])
    
    tasks = []
    for i in range(0, len(native_ver_arr), 2):
        idx = native_ver_arr[i]
        n_hash = native_ver_arr[i+1]
        if idx >= len(uuids): continue
        
        u = uuids[idx]
        p_info = paths.get(str(idx))[0] if str(idx) in paths else None
        res_type = types[paths.get(str(idx))[1]] if (str(idx) in paths and paths[str(idx)][1] < len(types)) else None
        i_hash = import_map.get(u, "")
        
        tasks.append((bundle_name, u, n_hash, i_hash, save_dir, p_info, res_type))

    # --- 核心：子进度条展示 ---
    if tasks:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(process_asset_task, t) for t in tasks]
            for _ in tqdm(concurrent.futures.as_completed(futures), total=len(tasks), desc=f"   ⬇️ {bundle_name}", leave=False, unit="file"):
                pass
    
    # 下载完成后，立即执行提取
    extract_spines_for_bundle(bundle_name, config, save_dir)
    pbar_main.update(1)

def main():
    print("=== DMM 终极整合下载器 (原生+Spine+双重进度条) ===")
    settings = get_settings_locally()
    if not settings: return

    bundle_vers = settings['assets']['bundleVers']
    bundles_to_run = TARGET_BUNDLES if TARGET_BUNDLES else list(bundle_vers.keys())

    with tqdm(total=len(bundles_to_run), unit="pkg", desc="📦 Total Bundles") as pbar:
        for b_name in bundles_to_run:
            if b_name in bundle_vers:
                process_bundle(b_name, bundle_vers[b_name], pbar)

    print("\n✅ 所有任务已完成！")

if __name__ == "__main__":
    main()
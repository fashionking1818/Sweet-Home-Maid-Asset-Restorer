import os
import requests
import json
import base64
import binascii
import urllib3
import concurrent.futures
import time # 👈 需要导入 time
from tqdm import tqdm

# ================= ⚙️ 配置区域 =================
BASE_RES_URL = "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/"
SETTINGS_URL = BASE_RES_URL + "src/settings.4229e.json"
DOWNLOAD_ROOT = "assets_restored" 
OVERWRITE = False
MAX_WORKERS = 8  # 👈 建议从 16 降到 8，提高稳定性

# 🎯 指定下载目标 (测试用)
# TARGET_BUNDLES = ["AdvStillstill102030"] 
TARGET_BUNDLES = ['Cardcard102032'] 

HEADERS = {
    "Host": "game.sweet-home-maid.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/index.html",
    "Connection": "keep-alive" # 保持连接
}
# ===============================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ... (decompress_uuid 和 decode_versions 函数保持不变，这里省略以节省篇幅) ...
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

# 🛠️ 核心修复：带重试机制的下载函数
def download_native_file(url, path):
    retries = 3
    for attempt in range(retries):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # 设置超时时间，防止挂死
            resp = requests.get(url, headers=HEADERS, verify=False, timeout=15)
            
            if resp.status_code == 200:
                with open(path, 'wb') as f:
                    f.write(resp.content)
                return True
            elif resp.status_code == 404:
                # 404 不需要重试，直接换下一个后缀
                return False
            else:
                # 500, 502, 503 等服务器错误，休眠后重试
                # print(f"⚠️ [Retry {attempt+1}] Status {resp.status_code}: {url}")
                time.sleep(1)
        
        except requests.exceptions.RequestException as e:
            # 网络报错（超时、连接断开），休眠后重试
            # print(f"⚠️ [Retry {attempt+1}] NetErr: {e}")
            time.sleep(1)
        except Exception as e:
            # 其他文件读写错误
            print(f"❌ Error: {e}")
            return False
            
    return False

def get_extension_by_type(resource_type):
    if not resource_type: return None
    if resource_type in ["cc.ImageAsset", "cc.Texture2D", "cc.SpriteFrame", "cc.SpriteAtlas", "cc.LabelAtlas"]:
        return ".png"
    elif resource_type in ["sp.SkeletonData", "dragonBones.DragonBonesData", "cc.BufferAsset"]:
        return ".bin"
    elif resource_type == "cc.AudioClip":
        return ".mp3"
    elif resource_type == "cc.TTFFont":
        return ".ttf"
    elif resource_type == "cc.ParticleAsset":
        return ".plist"
    elif resource_type == "cc.JsonAsset":
        return ".json"
    elif resource_type == "cc.TextAsset":
        return ".text" 
    return None

# ... (parse_import_data_in_memory 函数保持不变) ...
def parse_import_data_in_memory(json_data):
    try:
        native_ext = None
        resource_type = ""
        if isinstance(json_data, list) and len(json_data) >= 6:
            types_def = json_data[3]
            instances = json_data[5]
            if types_def and instances:
                if isinstance(types_def[0], list) and len(types_def[0]) > 0:
                     resource_type = types_def[0][0] 
                fields = types_def[0][1] 
                values = instances[0]     
                if "_native" in fields:
                    ext_idx = fields.index("_native") + 1
                    if ext_idx < len(values): 
                        native_ext = values[ext_idx]
        elif isinstance(json_data, dict):
            resource_type = json_data.get("__type__", "")
            native_ext = json_data.get("_native")
        if not native_ext:
            native_ext = get_extension_by_type(resource_type)
        return native_ext
    except:
        return None

def process_asset_task(args):
    bundle_name, compressed_uuid, native_hash, import_hash, save_dir, path_info, known_type = args
    real_uuid = decompress_uuid(compressed_uuid)
    
    import_prefix = compressed_uuid[:2] 
    native_prefix = real_uuid[:2]

    # 1. 优先使用 Config 中已知的类型
    ext_from_config = get_extension_by_type(known_type)
    
    ext_from_import = None
    if not ext_from_config and import_hash:
        import_url = f"{BASE_RES_URL}assets/{bundle_name}/import/{import_prefix}/{real_uuid}.{import_hash}.json"
        try:
            imp_resp = requests.get(import_url, headers=HEADERS, verify=False, timeout=10)
            if imp_resp.status_code == 200:
                import_data = imp_resp.json()
                ext_from_import = parse_import_data_in_memory(import_data)
        except:
            pass

    if path_info:
        real_name = path_info 
    else:
        real_name = real_uuid 

    exts_to_try = []

    if ext_from_config:
        exts_to_try.append(ext_from_config)
        # 针对图片，如果 .png 失败，一定要尝试 .jpg
        if ext_from_config == ".png": exts_to_try.extend([".jpg", ".webp", ".jpeg"])
        if ext_from_config == ".mp3": exts_to_try.extend([".ogg", ".wav"])

    if ext_from_import and ext_from_import not in exts_to_try:
        exts_to_try.append(ext_from_import)

    default_guesses = [".png", ".jpg", ".bin", ".atlas", ".txt", ".mp3", ".json", ".plist", ".ttf"]
    for g in default_guesses:
        if g not in exts_to_try:
            exts_to_try.append(g)

    native_prefix_url = f"{BASE_RES_URL}assets/{bundle_name}/native/{native_prefix}/{real_uuid}.{native_hash}"
    found = False

    for try_ext in exts_to_try:
        final_filename = f"{real_name}{try_ext}"
        final_path = os.path.join(save_dir, final_filename)
        
        if not OVERWRITE and os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            found = True
            break
            
        full_url = f"{native_prefix_url}{try_ext}"
        # 这里调用了新的 download_native_file，内部自带重试
        if download_native_file(full_url, final_path):
            found = True
            break 
    
    return found

# ... (process_bundle 和 main 函数保持不变) ...
def process_bundle(bundle_name, bundle_ver, pbar_main):
    if TARGET_BUNDLES and bundle_name not in TARGET_BUNDLES:
        pbar_main.update(1)
        return

    pbar_main.set_description(f"📂 {bundle_name}")
    save_dir = os.path.join(DOWNLOAD_ROOT, bundle_name)
    os.makedirs(save_dir, exist_ok=True)
    
    config_url = f"{BASE_RES_URL}assets/{bundle_name}/config.{bundle_ver}.json"
    try:
        resp = requests.get(config_url, headers=HEADERS, verify=False, timeout=10)
        if resp.status_code != 200: return
        config = resp.json()
    except:
        return

    uuids = config.get('uuids', [])
    paths = config.get('paths', {}) 
    types = config.get('types', [])
    
    import_vers_map = decode_versions(uuids, config.get('versions', {}).get('import', []))
    native_ver_arr = config.get('versions', {}).get('native', [])
    
    tasks = []
    
    for i in range(0, len(native_ver_arr), 2):
        idx = native_ver_arr[i]
        native_hash = native_ver_arr[i+1]
        
        if idx >= len(uuids): continue
            
        compressed_uuid = uuids[idx]
        
        path_info = None
        resource_type = None 
        
        str_idx = str(idx)
        if str_idx in paths:
            data_arr = paths[str_idx]
            if isinstance(data_arr, list) and len(data_arr) > 0:
                path_info = data_arr[0]
                if len(data_arr) > 1:
                    type_idx = data_arr[1]
                    if isinstance(type_idx, int) and type_idx < len(types):
                        resource_type = types[type_idx] 

        import_hash = import_vers_map.get(compressed_uuid, "")
        tasks.append((bundle_name, compressed_uuid, native_hash, import_hash, save_dir, path_info, resource_type))
        
    if not tasks:
        pbar_main.update(1)
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_asset_task, task) for task in tasks]
        concurrent.futures.wait(futures)
        
    pbar_main.update(1)

def main():
    print("=== DMM 资源下载器 (网络稳定版) ===")
    print(f"[-] 保存位置: {os.path.abspath(DOWNLOAD_ROOT)}")
    if TARGET_BUNDLES:
        print(f"[-] 🎯 仅下载目标: {TARGET_BUNDLES}")
    else:
        print(f"[-] 🚀 下载所有包")
    
    try:
        settings = requests.get(SETTINGS_URL, headers=HEADERS, verify=False).json()
        bundle_vers = settings['assets']['bundleVers']
    except Exception as e:
        print(f"[X] Settings 失败: {e}")
        return

    if TARGET_BUNDLES:
        total_tasks = len(TARGET_BUNDLES)
    else:
        total_tasks = len(bundle_vers)

    with tqdm(total=total_tasks, unit="pkg") as pbar:
        for b_name, b_ver in bundle_vers.items():
            process_bundle(b_name, b_ver, pbar)

    print("\n✅ 完成！")

if __name__ == "__main__":
    main()
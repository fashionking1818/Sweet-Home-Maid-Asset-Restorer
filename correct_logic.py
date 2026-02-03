import os
import requests
import json
import base64
import binascii
import urllib3
import concurrent.futures
from tqdm import tqdm

# ================= ⚙️ 配置区域 =================
BASE_RES_URL = "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/"
SETTINGS_URL = BASE_RES_URL + "src/settings.4229e.json"
DOWNLOAD_ROOT = "assets" # 可以改成之前的目录继续下载
OVERWRITE = False
MAX_WORKERS = 16

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

def download_native_file(url, path):
    try:
        resp = requests.get(url, headers=HEADERS, verify=False, timeout=20)
        if resp.status_code == 200:
            with open(path, 'wb') as f:
                f.write(resp.content)
            return True
        return False
    except:
        return False

# --- 核心修改：强制图片识别逻辑 ---

def parse_import_data_in_memory(json_data):
    """ 
    增强版解析：精准识别图片、Spine、音频，识别失败时才兜底
    """
    try:
        real_name = None
        native_ext = None
        resource_type = ""

        # --- 1. 数据结构解析 (兼容数组和字典) ---
        if isinstance(json_data, list) and len(json_data) >= 6:
            types_def = json_data[3]
            instances = json_data[5]
            if types_def and instances:
                # 提取类型字符串 (e.g. "cc.ImageAsset", "sp.SkeletonData")
                if isinstance(types_def[0], list) and len(types_def[0]) > 0:
                      resource_type = types_def[0][0] 
                
                fields = types_def[0][1] 
                values = instances[0]     
                
                if "_name" in fields:
                    name_idx = fields.index("_name") + 1
                    if name_idx < len(values): real_name = values[name_idx]
                if "_native" in fields:
                    ext_idx = fields.index("_native") + 1
                    if ext_idx < len(values): native_ext = values[ext_idx]

        elif isinstance(json_data, dict):
            resource_type = json_data.get("__type__", "")
            real_name = json_data.get("_name")
            native_ext = json_data.get("_native")

        # --- 2. 🚑 智能类型补全 (核心修改) ---
        # 如果 JSON 里没写后缀，根据 resource_type 决定
        if not native_ext:
            # [图片类] -> 强制 .png
            if resource_type in ["cc.ImageAsset", "cc.Texture2D", "cc.SpriteFrame", "cc.SpriteAtlas", "cc.LabelAtlas"]:
                native_ext = ".png"
            
            # [Spine 骨骼] -> 强制 .bin (绝大多数 DMM 游戏也是 .bin)
            elif resource_type in ["sp.SkeletonData", "dragonBones.DragonBonesData"]:
                native_ext = ".bin"
            
            # [音频] -> 强制 .mp3
            elif resource_type == "cc.AudioClip":
                native_ext = ".mp3"
            
            # [字体] -> 强制 .ttf
            elif resource_type == "cc.TTFFont":
                native_ext = ".ttf"
                
            # [粒子] -> 强制 .plist (通常粒子没有 native，但如果有，往往是 plist)
            elif resource_type == "cc.ParticleAsset":
                native_ext = ".plist"

        return real_name, native_ext
    except:
        return None, None
    
def process_asset_task(args):
    bundle_name, compressed_uuid, native_hash, import_hash, save_dir = args
    real_uuid = decompress_uuid(compressed_uuid)
    
    # 关键修正：Import 用压缩前缀，Native 用解压前缀
    import_prefix = compressed_uuid[:2] 
    native_prefix = real_uuid[:2]

    import_url = f"{BASE_RES_URL}assets/{bundle_name}/import/{import_prefix}/{real_uuid}.{import_hash}.json"
    try:
        imp_resp = requests.get(import_url, headers=HEADERS, verify=False, timeout=10)
        if imp_resp.status_code != 200: return False
        import_data = imp_resp.json()
    except:
        return False

    # 2. 解析类型和后缀
    real_name, ext = parse_import_data_in_memory(import_data)
    
    # 如果没有名字，用 UUID
    if not real_name: 
        real_name = real_uuid
    
    # 3. 构造下载列表 (智能回退策略)
    exts_to_try = []

    # A. 明确识别出的类型
    if ext == ".png":
        exts_to_try = [".png", ".jpg", ".webp"]
    elif ext == ".jpg":
        exts_to_try = [".jpg", ".png"]
    elif ext == ".bin":
        exts_to_try = [".bin", ".json"] # Spine 可能是 bin 也可能是 json
    elif ext == ".mp3":
        exts_to_try = [".mp3", ".ogg", ".wav", ".m4a"] # 音频四件套
    elif ext:
        exts_to_try = [ext]
    
    # B. [重要] 如果完全无法识别 (ext is None) -> 暴力盲猜
    # 优先猜图片，然后猜二进制(Spine)，最后猜音频
    else:
        exts_to_try = [".png", ".jpg", ".bin", ".mp3", ".json"]

    # 4. 循环下载，直到命中
    native_prefix_url = f"{BASE_RES_URL}assets/{bundle_name}/native/{native_prefix}/{real_uuid}.{native_hash}"
    found = False

    for try_ext in exts_to_try:
        final_filename = f"{real_name}{try_ext}"
        final_path = os.path.join(save_dir, final_filename)
        
        # 续传检查
        if not OVERWRITE and os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            found = True
            break
            
        full_url = f"{native_prefix_url}{try_ext}"
        if download_native_file(full_url, final_path):
            found = True
            break # 成功一个就收工
    
    return found

def process_bundle(bundle_name, bundle_ver, pbar_main):
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
    import_vers = decode_versions(uuids, config.get('versions', {}).get('import', []))
    native_vers = decode_versions(uuids, config.get('versions', {}).get('native', []))
    
    tasks = []
    for compressed_uuid, native_hash in native_vers.items():
        import_hash = import_vers.get(compressed_uuid)
        if not import_hash: continue
        tasks.append((bundle_name, compressed_uuid, native_hash, import_hash, save_dir))
        
    if not tasks:
        pbar_main.update(1)
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_asset_task, task) for task in tasks]
        concurrent.futures.wait(futures)
        
    pbar_main.update(1)

def main():
    print("=== DMM 资源下载器 (强制下载版) ===")
    print(f"[-] 保存位置: {os.path.abspath(DOWNLOAD_ROOT)}")
    
    try:
        settings = requests.get(SETTINGS_URL, headers=HEADERS, verify=False).json()
        bundle_vers = settings['assets']['bundleVers']
    except Exception as e:
        print(f"[X] Settings 失败: {e}")
        return

    with tqdm(total=len(bundle_vers), unit="pkg") as pbar:
        for b_name, b_ver in bundle_vers.items():
            process_bundle(b_name, b_ver, pbar)

    print("\n✅ 完成！Ability 文件夹现在应该有文件了 (即使名字是 UUID)。")

if __name__ == "__main__":
    main()

import json
import os
import base64
import binascii
from moviepy.editor import ImageClip, concatenate_videoclips

# ================= ⚙️ 配置区域 =================
CONFIG_DIR = "configs"        
IMPORT_ROOT = "imports"       
# ===============================================

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

def find_animation_data(data):
    """递归查找包含 'stillPathList' 的配置节点 """
    if isinstance(data, dict):
        if "stillPathList" in data and "animation" in data:
            return data
        for value in data.values():
            result = find_animation_data(value)
            if result: return result
    elif isinstance(data, list):
        for item in data:
            result = find_animation_data(item)
            if result: return result
    return None

def get_animation_config(bundle_name):
    """根据 Bundle 名自动定位包含动画信息的 JSON """
    target_dir = os.path.join(CONFIG_DIR, bundle_name)
    if not os.path.exists(target_dir):
        print(f"❌ 找不到 Bundle 目录: {target_dir}")
        return None

    cfg_path = next((os.path.join(target_dir, f) for f in os.listdir(target_dir) if f.startswith("config.")), None)
    if not cfg_path: return None

    with open(cfg_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 1. 寻找 cc.JsonAsset 的索引 
    try:
        json_type_idx = config.get("types", []).index("cc.JsonAsset")
    except ValueError:
        return None

    # 2. 筛选出所有 JsonAsset 资源 
    uuids = config.get("uuids", [])
    paths = config.get("paths", {})
    import_vers = config.get("versions", {}).get("import", [])
    ver_map = {import_vers[i]: import_vers[i+1] for i in range(0, len(import_vers), 2)}

    for str_idx, info in paths.items():
        if len(info) > 1 and info[1] == json_type_idx:
            idx = int(str_idx)
            uuid_str = uuids[idx]
            file_hash = ver_map.get(idx)
            if not file_hash: continue

            real_uuid = decompress_uuid(uuid_str)
            prefix = uuid_str[:2]
            
            # 拼接 Import 路径 
            import_path = os.path.join(IMPORT_ROOT, bundle_name, "import", prefix, f"{real_uuid}.{file_hash}.json")
            if not os.path.exists(import_path):
                import_path = os.path.join(IMPORT_ROOT, bundle_name, "import", prefix, f"{uuid_str}.{file_hash}.json")

            if os.path.exists(import_path):
                with open(import_path, 'r', encoding='utf-8') as f:
                    import_data = json.load(f)
                anim_config = find_animation_data(import_data)
                if anim_config:
                    print(f"✅ 已自动定位动画配置: {os.path.basename(import_path)}")
                    return anim_config
    return None

def main():
    print("=== DMM 自动视频合成工具 (Bundle 模式) ===")
    
    bundle_name = input("请输入 Bundle 名称 (例如 AdvStillstill101005): ").strip()
    img_dir = input("请输入 [图片所在文件夹] 的完整路径: ").strip().strip('"')

    if not os.path.exists(img_dir):
        print("错误：图片文件夹不存在。")
        return

    # 自动获取配置 [cite: 1, 2]
    config = get_animation_config(bundle_name)
    if not config:
        print("错误：无法在该 Bundle 中找到动画数据。")
        return

    path_list = config["stillPathList"]
    anim_dict = config["animation"]
    anim_names = list(anim_dict.keys())

    print(f"\n检测到 {len(anim_names)} 个动画片段:")
    for idx, name in enumerate(anim_names):
        print(f"  [{idx + 1}] {name}")
    
    try:
        choice = int(input("\n请选择要合成的动画序号: ")) - 1
        target_name = anim_names[choice]
    except (ValueError, IndexError):
        print("选择无效。")
        return

    anim_data = anim_dict[target_name]
    keys = anim_data.get("keys", [])
    if not keys: return

    # 渲染逻辑 (沿用原 video_maker) 
    clips = []
    default_duration = 0.033 
    print(f"正在处理 [{target_name}]...")

    for i in range(len(keys)):
        curr_key = keys[i]
        img_idx = curr_key.get("idx", 0)
        base_name = path_list[img_idx]
        
        img_path = os.path.join(img_dir, base_name + ".jpg")
        if not os.path.exists(img_path):
            img_path = os.path.join(img_dir, base_name + ".png")
        
        if not os.path.exists(img_path):
            continue

        duration = default_duration
        if i < len(keys) - 1:
            diff = keys[i+1].get("time", 0) - curr_key.get("time", 0)
            if diff > 0.001: duration = diff
        
        clips.append(ImageClip(img_path).set_duration(duration))

    if not clips:
        print("没有可合成的帧。")
        return

    final_clip = concatenate_videoclips(clips, method="compose")
    output_path = os.path.join(img_dir, f"{target_name}_output.mp4")
    final_clip.write_videofile(output_path, fps=30, codec="libx264", audio=False)
    print(f"\n✅ 成功！文件保存在: {output_path}")

if __name__ == "__main__":
    main()
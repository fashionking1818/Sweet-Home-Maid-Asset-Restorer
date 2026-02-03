import os
import json
import base64
import binascii

# ================= ⚙️ 配置区域 =================
CONFIG_DIR = "configs"        
IMPORT_ROOT = "imports"       
OUTPUT_ROOT = "assets_restored"  
# ===============================================

def decompress_uuid(uuid_str):
    """ 解压 UUID 以匹配文件名 """
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

def find_config_file(bundle_name):
    target_dir = os.path.join(CONFIG_DIR, bundle_name)
    if not os.path.exists(target_dir):
        return None
    for f in os.listdir(target_dir):
        if f.startswith("config.") and f.endswith(".json"):
            return os.path.join(target_dir, f)
    return None

def recursive_find_skeleton(d):
    """ 
    [核心修正] 递归查找包含 Spine 数据的字典 
    结构特征: 字典包含 "skeleton"(dict) 和 "bones"(list) 作为顶层键
    """
    if isinstance(d, dict):
        # 特征匹配：skeleton 和 bones 是兄弟节点
        if "skeleton" in d and "bones" in d:
            if isinstance(d["skeleton"], dict) and isinstance(d["bones"], list):
                return d
        
        # 递归遍历字典的值
        for k, v in d.items():
            res = recursive_find_skeleton(v)
            if res: return res

    elif isinstance(d, list):
        # 递归遍历列表的元素
        for item in d:
            res = recursive_find_skeleton(item)
            if res: return res
    
    return None

def extract_spine_from_bundle(bundle_name):
    print(f"\n🔍 正在分析 Bundle: {bundle_name}")
    
    cfg_path = find_config_file(bundle_name)
    if not cfg_path:
        print(f"❌ 找不到 {bundle_name} 的 Config 文件。")
        return

    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ 读取 Config 失败: {e}")
        return

    # 定位类型索引
    types = config.get("types", [])
    try:
        spine_type_idx = types.index("sp.SkeletonData")
    except ValueError:
        print("⚠️ 该 Bundle 中不包含 'sp.SkeletonData'。")
        return

    # 解析 paths
    paths = config.get("paths", {})
    target_uuid_indices = []
    for str_idx, info in paths.items():
        if len(info) > 1 and info[1] == spine_type_idx:
            target_uuid_indices.append(int(str_idx))

    if not target_uuid_indices:
        print("⚠️ 未在 paths 中找到 Spine 资源引用。")
        return

    print(f"[-] 找到 {len(target_uuid_indices)} 个 Spine 资源，开始提取...")

    # Version Map
    uuids_list = config.get("uuids", [])
    import_vers = config.get("versions", {}).get("import", [])
    ver_map = {}
    for i in range(0, len(import_vers), 2):
        ver_map[import_vers[i]] = import_vers[i+1]

    save_dir = os.path.join(OUTPUT_ROOT, bundle_name)
    os.makedirs(save_dir, exist_ok=True)
    success_count = 0

    for idx in target_uuid_indices:
        if idx >= len(uuids_list): continue
        
        uuid_str = uuids_list[idx]
        file_hash = ver_map.get(idx)
        
        # 获取文件名 (优先使用 paths 里的名字)
        path_info = paths.get(str(idx))
        original_name = path_info[0] if path_info else f"spine_{idx}"
        original_name = original_name.replace("/", "_") # 防止路径报错

        if not file_hash:
            continue

        real_uuid = decompress_uuid(uuid_str)
        prefix = uuid_str[:2]
        
        possible_paths = [
            os.path.join(IMPORT_ROOT, f"{bundle_name}/import/{prefix}/{real_uuid}.{file_hash}.json"),
            os.path.join(IMPORT_ROOT, f"{bundle_name}/import/{prefix}/{uuid_str}.{file_hash}.json")
        ]
        
        json_path = None
        for p in possible_paths:
            if os.path.exists(p):
                json_path = p
                break
        
        if not json_path:
            print(f"❌ 文件缺失: {real_uuid}.{file_hash}.json")
            continue

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # [策略 A] 直接定位 (针对你的文件结构 data[5][0][4])
            # 你的文件里: Element 5 是 list, Element 5[0] 是 Instance, 里面的 Index 4 是 Spine Dict
            spine_data = None
            try:
                # 尝试直接读取数组结构，这比递归快且准
                if isinstance(data, list) and len(data) >= 6:
                    instances = data[5]
                    if isinstance(instances, list) and len(instances) > 0:
                        first_instance = instances[0]
                        if isinstance(first_instance, list) and len(first_instance) >= 5:
                            candidate = first_instance[4]
                            if isinstance(candidate, dict) and "skeleton" in candidate and "bones" in candidate:
                                spine_data = candidate
            except:
                pass

            # [策略 B] 如果 A 失败，使用修正后的递归
            if not spine_data:
                spine_data = recursive_find_skeleton(data)
            
            if spine_data:
                output_path = os.path.join(save_dir, f"{original_name}.json")
                with open(output_path, 'w', encoding='utf-8') as f_out:
                    json.dump(spine_data, f_out, indent=2, ensure_ascii=False)
                success_count += 1
                print(f"   ✅ 提取成功: {original_name}.json")
            else:
                print(f"   ⚠️ 解析失败 (深度搜索未找到特征): {os.path.basename(json_path)}")

        except Exception as e:
            print(f"   ❌ 处理出错: {e}")

    print(f"\n🎉 处理完成！共提取 {success_count} 个骨骼文件。")
    print(f"📁 保存位置: {os.path.abspath(save_dir)}")

def main():
    print("=== DMM Spine 自动提取器 (Fixed v2) ===")
    
    while True:
        target = input("\n请输入要提取的 Bundle 名称 (输入 q 退出): ").strip()
        if target.lower() == 'q': break
        if not target: continue
        
        extract_spine_from_bundle(target)

if __name__ == "__main__":
    main()
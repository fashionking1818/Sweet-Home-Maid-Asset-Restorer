import os
import json
import re
import requests
import urllib3

# ================= ⚙️ 配置 =================
# 你下载资源的根目录 (脚本会扫描这个目录下所有的 .json 和 .cconb)
ASSETS_ROOT = r"D:\Workspace\VSCode\Scripts\sweethomemaid\Raw_Assets_Binary\main" 
# 如果发现缺少的 .bin 文件，去哪里下载 (基础 URL)
BASE_RES_URL = "https://game.sweet-home-maid.com/r/7LCHDxB8msHV/"
# 提取出的 Spine 保存位置
OUTPUT_DIR = "Extracted_Spine"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://game.sweet-home-maid.com/",
}
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# ===========================================

def parse_cconb(file_path):
    """
    黑科技：将 CCONB (Cocos Binary) 清洗为可读 JSON
    原理：CCONB 头部包含一些二进制标记，后面紧跟标准 JSON 字符串
    """
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        # 1. 尝试寻找 JSON 的开始标记 '[' 或 '{'
        # CCONB 文件头通常以 'CCON' 开头，后面跟着一些字节
        start_idx = -1
        for i in range(min(len(content), 100)):
            if content[i] == 123 or content[i] == 91: # '{' or '['
                start_idx = i
                break
        
        if start_idx != -1:
            json_str = content[start_idx:].decode('utf-8', errors='ignore')
            # 有时候末尾会有零填充，去掉
            json_str = json_str.strip('\x00')
            return json.loads(json_str)
    except Exception as e:
        # print(f"解析失败 {file_path}: {e}")
        pass
    return None

def download_bin(uuid, native_path, save_path):
    """ 下载缺失的 .bin (Skel) 文件 """
    # native_path 格式通常是 ".bin" 或者具体哈希 ".12345.bin"
    # 我们需要根据 uuid 构造 URL
    if os.path.exists(save_path): return True
    
    # 尝试构造 URL
    # 这里比较麻烦，因为我们不知道 config 里的 hash。
    # 但我们可以利用 "盲猜" 策略，或者假设 native_path 里包含了 hash (如果之前下载器保存了原始文件名)
    
    # 如果之前的下载器已经把文件下到了 assets/bundle/native/xx/uuid.hash.bin
    # 我们直接去搜索本地文件更稳妥
    return False

def find_local_native_file(uuid, bundle_path):
    """ 在本地 native 文件夹里搜索对应 UUID 的文件 """
    # 假设之前的下载器已经把 native 文件下下来了，可能后缀是 .bin 或 .unk
    # 你的下载器保存结构是 assets/bundle_name/filename.ext
    # 我们需要遍历一下
    for root, dirs, files in os.walk(bundle_path):
        for f in files:
            if uuid in f and (f.endswith('.bin') or f.endswith('.skel')):
                return os.path.join(root, f)
    return None

def extract_spine(data, file_uuid, bundle_name, save_dir):
    """ 从 JSON 数据中提取 Spine """
    # Cocos 3.x 数据结构通常是数组: [type_def, ..., instances]
    # 或者直接是对象
    
    skel_data = None
    atlas_text = None
    texture_uuids = []
    native_ref = None # 指向 .bin 文件

    # --- 解析数据结构 ---
    if isinstance(data, list) and len(data) >= 5:
        # 压缩格式
        instances = data[5]
        if not instances: return
        inst = instances[0] # 通常第一个是主数据
        
        # 我们需要找到 sp.SkeletonData 对应的字段
        # 这比较复杂，我们用暴力搜索：找包含 _atlasText 的字段
        
        # 搜索 atlas 文本
        for item in inst:
            if isinstance(item, str):
                if "format: RGBA8888" in item and "size:" in item:
                    atlas_text = item
                elif item.endswith('.bin'):
                    native_ref = item
        
        # 搜索 textures (通常是一个数组，里面全是 UUID)
        for item in inst:
            if isinstance(item, list) and len(item) > 0 and isinstance(item[0], str):
                # 假设这是 texture uuid 列表 (特征不明显，可能有误判)
                pass

    elif isinstance(data, dict):
        # 字典格式 (更易读)
        if data.get("__type__") == "sp.SkeletonData":
            atlas_text = data.get("_atlasText")
            native_ref = data.get("_native") # 通常是 ".bin"
            textures = data.get("textures")
            if textures:
                texture_uuids = [t["__uuid__"] for t in textures]
    
    # --- 执行提取 ---
    if atlas_text: # 只要有 Atlas 文本，大概率就是 Spine 数据
        print(f"🔥 发现 Spine: {file_uuid} ({bundle_name})")
        
        real_name = file_uuid # 暂时用 UUID 命名
        
        # 1. 保存 Atlas
        atlas_path = os.path.join(save_dir, f"{real_name}.atlas")
        with open(atlas_path, "w", encoding="utf-8") as f:
            f.write(atlas_text)
        print(f"  -> 导出 Atlas: {real_name}.atlas")

        # 2. 寻找并复制 Skel (.bin)
        # 之前的下载器如果成功下载了 native 文件，我们就在本地找
        # Cocos 3.x 的 native 引用通常只是后缀，比如 ".bin"
        # 真正的文件是 UUID.hash.bin
        
        # 在 assets/bundle_name 目录下搜索包含此 UUID 的 .bin 文件
        bundle_path = os.path.join(ASSETS_ROOT, bundle_name)
        bin_file = find_local_native_file(file_uuid, bundle_path)
        
        if bin_file:
            import shutil
            target_bin = os.path.join(save_dir, f"{real_name}.skel") # 改名为 .skel 方便查看器识别
            shutil.copy(bin_file, target_bin)
            print(f"  -> 关联 Skel: {os.path.basename(bin_file)}")
        else:
            print(f"  [!] 警告: 找不到本地 .bin 文件，可能之前下载失败: {file_uuid}")

        # 3. 寻找关联图片
        # 简单粗暴法：Atlas 里记录了图片名叫什么 (例如 "tex.png")
        # 我们去 bundle 文件夹里找有没有同名的图片，或者用 UUID 匹配
        # 这里建议手动把同 bundle 的图片都拷过来，因为匹配逻辑很复杂
        
def main():
    if not os.path.exists(ASSETS_ROOT):
        print(f"错误: 找不到 {ASSETS_ROOT} 文件夹")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("=== 开始扫描 CCONB 并提取 Spine ===")
    
    # 遍历所有 Bundle
    for bundle in os.listdir(ASSETS_ROOT):
        bundle_path = os.path.join(ASSETS_ROOT, bundle)
        if not os.path.isdir(bundle_path): continue
        
        print(f"📂 扫描包: {bundle}")
        
        # 遍历包内文件
        for fname in os.listdir(bundle_path):
            if fname.endswith(".json") or fname.endswith(".cconb"):
                fpath = os.path.join(bundle_path, fname)
                uuid = os.path.splitext(fname)[0] # 去掉后缀作为 UUID
                
                # 1. 解析 CCONB/JSON
                data = parse_cconb(fpath)
                if not data: continue
                
                # 2. 尝试提取
                extract_spine(data, uuid, bundle, OUTPUT_DIR)

    print(f"\n✅ 提取完成！请查看 {OUTPUT_DIR} 文件夹")
    print("注意：如果 .skel 文件缺失，请确保之前的下载器脚本里的 '强制下载 .bin' 逻辑已生效。")

if __name__ == "__main__":
    main()
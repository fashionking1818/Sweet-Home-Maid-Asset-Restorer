import os
import json
from tqdm import tqdm

# ================= ⚙️ 配置区域 =================
# 输入下载好的资源根目录文件夹名称
TARGET_DIR = input("资源根目录文件夹（configs，imports等等）：")

# 缩进空格数 (VSCode 默认通常是 2 或 4)
INDENT_SIZE = 4 
# ===============================================

def format_local_json_files():
    if not os.path.exists(TARGET_DIR):
        print(f"❌ 错误：找不到文件夹 '{TARGET_DIR}'，请检查配置。")
        return

    # 1. 扫描所有 json 文件
    print(f"[-] 正在扫描目录: {os.path.abspath(TARGET_DIR)} ...")
    json_files_list = []
    
    for root, dirs, files in os.walk(TARGET_DIR):
        for file in files:
            if file.lower().endswith(".json"):
                full_path = os.path.join(root, file)
                json_files_list.append(full_path)

    if not json_files_list:
        print("⚠️ 未找到任何 JSON 文件。")
        return

    print(f"[-] 找到 {len(json_files_list)} 个 JSON 文件，开始格式化...")

    # 2. 批量处理
    success_count = 0
    error_count = 0

    for file_path in tqdm(json_files_list, unit="file"):
        try:
            # 读取原始数据
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 重新写入（带格式化）
            with open(file_path, 'w', encoding='utf-8') as f:
                # indent=INDENT_SIZE: 开启缩进
                # ensure_ascii=False: 保证中文/日文正常显示，不会变成 \uXXXX
                json.dump(data, f, indent=INDENT_SIZE, ensure_ascii=False)
            
            success_count += 1
            
        except Exception as e:
            error_count += 1
            tqdm.write(f"[!] 处理失败: {file_path} -> {e}")

    print("\n" + "="*30)
    print(f"✅ 处理完成！")
    print(f"成功: {success_count}")
    print(f"失败: {error_count}")
    print("现在用 VSCode 打开文件夹，JSON 应该已经自动分行并着色了。")

if __name__ == "__main__":
    format_local_json_files()
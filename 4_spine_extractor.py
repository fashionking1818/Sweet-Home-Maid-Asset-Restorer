import json
import os
import sys

def clean_path(path_str):
    """清理路径字符串（去除引号和空白）"""
    return path_str.strip().strip('"').strip("'")

def extract_spine_data():
    print("=== Cocos Spine 骨骼提取工具 (仅提取JSON) ===")
    
    # 1. 获取输入路径
    while True:
        json_path_input = input("\n请输入 [Spine数据 json] 的完整路径: ")
        json_path = clean_path(json_path_input)
        
        if os.path.exists(json_path):
            break
        print("❌ 错误：文件不存在，请重新输入。")

    # 2. 获取输出路径
    while True:
        output_dir_input = input("请输入 [输出文件夹] 的路径 (直接回车 = 保存在原目录下): ")
        output_dir = clean_path(output_dir_input)
        
        # 如果用户直接回车，默认为源文件目录
        if not output_dir:
            output_dir = os.path.dirname(json_path)
            print(f"👉 将保存在默认目录: {output_dir}")
            break
        
        # 如果用户输入了路径，检查是否存在，不存在则创建
        try:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                print(f"📁 检测到目录不存在，已自动创建: {output_dir}")
            break
        except Exception as e:
            print(f"❌ 错误：无法创建或访问该目录 ({e})，请重新输入。")

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return

    # 3. 定位数据核心
    target_data = None
    
    # 策略 A: 针对你提供的 config 结构 (data[5][0])
    try:
        if len(data) >= 6:
            potential_data = data[5][0]
            if isinstance(potential_data, list) and \
               len(potential_data) > 4 and \
               isinstance(potential_data[2], str) and \
               "size:" in potential_data[2] and \
               isinstance(potential_data[4], dict) and \
               "skeleton" in potential_data[4]:
                target_data = potential_data
    except:
        pass

    # 策略 B: 深度搜索 (如果结构变化)
    if not target_data:
        print("⚠️ 标准位置未找到数据，正在尝试深度搜索...")
        def recursive_search(d):
            if isinstance(d, list):
                # 特征: 列表长度>4, index 2包含 "size:", index 4包含 "skeleton"
                if len(d) > 4 and \
                   isinstance(d[2], str) and "size:" in d[2] and \
                   isinstance(d[4], dict) and "skeleton" in d[4]:
                    return d
                for item in d:
                    res = recursive_search(item)
                    if res: return res
            return None
        
        target_data = recursive_search(data)

    if not target_data:
        print("❌ 无法在文件中解析出 Spine 数据结构。请确认这是有效的 Cocos SkeletonData 导出文件。")
        return

    # 4. 提取字段
    # index 1: _name
    # index 4: _skeletonJson (骨骼数据)
    spine_name = target_data[1]
    skeleton_data = target_data[4]

    print(f"\n✅ 成功解析数据！")
    print(f"   角色名称: {spine_name}")
    print(f"   (Atlas 数据已跳过)")

    # 5. 保存文件到指定目录
    skeleton_filename = f"{spine_name}.json"
    skeleton_path = os.path.join(output_dir, skeleton_filename)

    try:
        # 写入 skeleton json
        with open(skeleton_path, 'w', encoding='utf-8') as f:
            json.dump(skeleton_data, f, indent=2, ensure_ascii=False)

        print(f"\n🎉 提取完成！")
        print(f"   已生成: {skeleton_path}")
        
    except Exception as e:
        print(f"❌ 写入文件时出错: {e}")

if __name__ == "__main__":
    extract_spine_data()
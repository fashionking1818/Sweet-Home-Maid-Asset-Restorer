import json
import os
import sys
from moviepy.editor import ImageClip, concatenate_videoclips

def find_animation_data(data):
    """递归查找包含 'stillPathList' 的配置节点"""
    if isinstance(data, dict):
        if "stillPathList" in data and "animation" in data:
            return data
        for key, value in data.items():
            result = find_animation_data(value)
            if result: return result
    elif isinstance(data, list):
        for item in data:
            result = find_animation_data(item)
            if result: return result
    return None

def clean_path(path_str):
    """清理用户输入的路径（去除引号和空白）"""
    return path_str.strip().strip('"').strip("'")

def get_image_files(img_dir):
    """获取文件夹下所有图片并排序"""
    valid_exts = ('.jpg', '.png', '.jpeg', '.bmp')
    files = [f for f in os.listdir(img_dir) if f.lower().endswith(valid_exts)]
    # 简单的文件名排序，如果文件名是纯数字序列（如 1.jpg, 2.jpg, 10.jpg），
    # 默认的字符串排序会导致 1, 10, 2。
    # 这里尝试做一个简单的自然排序优化，如果不是数字则按默认ASCII排序
    try:
        files.sort(key=lambda x: int(os.path.splitext(x)[0]))
    except ValueError:
        files.sort()
    return files

def main():
    print("=== 动画/视频资源合成工具 ===")
    print("1. Cocos JSON 模式 (读取 JSON 关键帧)")
    print("2. 文件夹序列帧模式 (指定文件夹下所有图片按文件名排序, 30fps)")
    
    mode = input("\n请选择模式 (输入 1 或 2): ").strip()
    
    # 初始化变量
    clips = []
    target_name = "output"
    img_dir = ""

    # ==========================
    # 模式 1: JSON 动画逻辑
    # ==========================
    if mode != "2": 
        # 1. 获取输入路径
        while True:
            json_path_input = input("\n请输入 [animation json] 的完整路径: ")
            json_path = clean_path(json_path_input)
            if os.path.exists(json_path):
                break
            print("错误：文件不存在，请重新输入。")

        while True:
            img_dir_input = input("请输入 [图片所在文件夹] 的完整路径: ")
            img_dir = clean_path(img_dir_input)
            if os.path.exists(img_dir):
                break
            print("错误：文件夹不存在，请重新输入。")

        # 2. 读取并解析数据
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
        except Exception as e:
            print(f"读取 JSON 失败: {e}")
            return

        config = find_animation_data(raw_data)
        if not config:
            print("错误：无法在该 JSON 中解析出 animation 数据结构。")
            return

        path_list = config["stillPathList"]
        anim_dict = config["animation"]

        # 3. 列出可用动画并让用户选择
        anim_names = list(anim_dict.keys())
        print(f"\n检测到包含 {len(anim_names)} 个动画片段:")
        for idx, name in enumerate(anim_names):
            print(f"  [{idx + 1}] {name}")
        
        selected_idx = -1
        while True:
            try:
                choice = input("\n请输入序号选择要合成的动画: ")
                selected_idx = int(choice) - 1
                if 0 <= selected_idx < len(anim_names):
                    break
            except ValueError:
                pass
            print("输入无效，请输入正确的序号。")

        target_name = anim_names[selected_idx]
        anim_data = anim_dict[target_name]
        keys = anim_data.get("keys", [])

        if not keys:
            print("该片段没有关键帧数据！")
            return
            
        print(f"\n正在处理 [{target_name}]，共 {len(keys)} 帧...")
        
        # 处理 JSON 关键帧
        default_duration = 0.033 
        for i in range(len(keys)):
            current_key = keys[i]
            img_idx = current_key.get("idx", 0)
            if img_idx >= len(path_list): continue
                
            base_name = path_list[img_idx]
            img_path = os.path.join(img_dir, base_name + ".jpg")
            if not os.path.exists(img_path):
                img_path = os.path.join(img_dir, base_name + ".png")
            
            if not os.path.exists(img_path):
                print(f"  [跳过] 找不到图片: {base_name}")
                continue

            # 计算时长
            current_time = current_key.get("time", 0)
            duration = default_duration

            if i < len(keys) - 1:
                next_key = keys[i+1]
                next_time = next_key.get("time", 0)
                diff = next_time - current_time
                if diff > 0.001:
                    duration = diff
            
            clips.append(ImageClip(img_path).set_duration(duration))

    # ==========================
    # 模式 2: 文件夹直接合成逻辑
    # ==========================
    else:
        while True:
            img_dir_input = input("\n请输入 [图片所在文件夹] 的完整路径: ")
            img_dir = clean_path(img_dir_input)
            if os.path.exists(img_dir):
                break
            print("错误：文件夹不存在，请重新输入。")
            
        print("\n正在扫描图片...")
        image_files = get_image_files(img_dir)
        
        if not image_files:
            print("错误：该文件夹下没有找到 jpg/png 图片。")
            return
            
        print(f"找到 {len(image_files)} 张图片，将按文件名顺序合成。")
        
        # 设置固定帧率 30fps
        duration = 1.0 / 30.0
        target_name = os.path.basename(img_dir) or "folder_sequence"
        
        for img_file in image_files:
            img_path = os.path.join(img_dir, img_file)
            clips.append(ImageClip(img_path).set_duration(duration))

    # ==========================
    # 公共导出逻辑
    # ==========================
    if not clips:
        print("没有生成任何有效片段。")
        return

    # 选择输出格式
    out_format = input("\n输出格式? (1: MP4 [默认], 2: GIF): ").strip()
    is_gif = out_format == "2"

    final_clip = concatenate_videoclips(clips, method="compose")
    
    output_filename = f"{target_name}_output.{'gif' if is_gif else 'mp4'}"
    output_path = os.path.join(img_dir, output_filename)

    print(f"\n正在渲染，请稍候...")
    
    if is_gif:
        final_clip.write_gif(output_path, fps=15)
    else:
        # MP4 统一使用 30fps
        final_clip.write_videofile(output_path, fps=30, codec="libx264", audio=False)

    print(f"\n✅ 成功！文件已保存至:\n{output_path}")

if __name__ == "__main__":
    main()
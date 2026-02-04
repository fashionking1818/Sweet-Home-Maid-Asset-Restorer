import os

target_dir = input('请输入要清理的目录：')

# topdown=False 确保先遍历子目录（自底向上）
for root, dirs, files in os.walk(target_dir, topdown=False):
    for name in dirs:
        d_path = os.path.join(root, name)
        # 尝试删除，os.rmdir 只能删除空目录，非空会抛出 OSError
        try:
            os.rmdir(d_path)
            print(f"已删除空目录: {d_path}")
        except OSError:
            pass # 目录非空，跳过
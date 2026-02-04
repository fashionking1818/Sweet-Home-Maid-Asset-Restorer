# Sweet Home Maid Asset Restorer

这是一个尝试还原 スイートホームメイド 资源的工具集。

它能够从服务端抓取散碎的 json、Spine、图片、音频这些美术相关资源，并根据 `config` 和 `import` 数据将其还原为可读的文件名，同时支持自动提取 Spine 骨骼动画数据和合成 ADV 剧情视频。但是仍有不完善的地方，而且本人没有体验过游戏，不确定是否存在漏掉的资源😃。

## 主要功能

* **智能还原文件名**：利用 `config.json` 中的 `paths` 映射，将压缩过的的 UUID (如 `076f221e4`) 还原为真实文件名 (如 `102005_6`) [cite: 1, 2]。
  
* **精准后缀识别**：通过预下载 `import` 数据读取 `_native` 字段，精准识别 `.atlas`, `.mp3` 等真实后缀 。
  
* **Spine 骨骼提取**：自动递归查找资源中的 `skeleton` 和 `bones` 数据结构，提取并保存为标准的 Spine JSON 格式 。
  
* **ADV 视频合成**：解析 ADV 剧情脚本中的 `stillPathList` 和 `animation` 时间轴，将序列帧图片自动合成为 MP4 视频 。
  
* **断点续传**：支持本地缓存索引，已下载的文件自动跳过。

## 环境准备

1. 安装 Python 3.8+
2. 安装依赖库：
   ```bash
   pip install -r requirements.txt

## 使用顺序

1. 使用 `1_config_downloader.py` 下载配置映射。
   
2. 使用 `2_import_downloader.py` 下载 import 文件夹，其中会使用到1中下载的 config 文件。
   
3. 使用 `5_bundle_and_spine.py` 尝试下载所有资源或者指定包名
   
   包名请查看 `settings.xxxx.json` 中的assets.bundleVers 字段中的“AdvStillstill1001”这种，不需要后面的hash值（有全部包名）。
   
   ❗注意：由于网络原因可能会导致某些资源下载失败。

4. （可选）使用 `4_video_maker.py` 恢复动画

5. 可以使用 `9_json_helper.py` 将指定目录下的 json 文件分行，`9_rm_empty_dirs.py` 清空指定目录下的空文件夹

## ⚠️ 免责声明 (Disclaimer)

1.  **仅供学习研究**：本项目仅供 Python 爬虫技术交流与逆向分析学习使用，请勿用于任何商业用途或非法目的。
   
2.  **后果自负**：使用者在使用本工具时产生的一切后果（包括但不限于账号封禁、IP 被锁、法律纠纷等）由使用者自行承担，作者不承担任何责任。

3.  **版权归属**：本项目所提取的所有资源（图片、音频、文本等）版权均归游戏开发商及运营商所有。请在下载后 24 小时内删除，如果您喜欢该游戏，请支持正版。
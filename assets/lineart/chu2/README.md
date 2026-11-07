# CHU2 矢量线稿

`chu2-lineart.svg` 是用于本 PCB 人物丝印的矢量轮廓素材，不是官方原始矢量文件。正面人物填充与背面头像由 `tools/front_person.py` 和 `tools/back_portrait.py` 从此 SVG 转换为毫米布局，输出保存在 `layout/front.json` 和 `layout/back.json`。PCB 构建直接读取布局文件。

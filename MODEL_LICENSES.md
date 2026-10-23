# 固定模型清单与许可状态

以下六权重不随源码包分发。模型内容、摘要、分类标签和输入输出均沿用1.3；没有更换模型或重新校准。manifest 中的 license 记录 MTG 官方概览的声明，不是五份官方 JSON 中的许可字段（这些 JSON 没有该字段），也不是新的授权；不能覆盖 LICENSE_STATUS.md 列出的冲突。

|用途|文件|字节数|SHA256|发布方许可/状态|来源|
|---|---|---:|---|---|---|
|effnet|discogs-effnet-bsdynamic-1.onnx|18027718|a280825b334797cf677939db8cd5762c0392aedd0ca6415dbc1cd083f045e43c|CC BY-NC-SA 4.0；与原ND文本冲突未解决|[固定下载源](https://essentia.upf.edu/models/feature-extractors/discogs-effnet/discogs-effnet-bsdynamic-1.onnx)|
|moodtheme|mtg_jamendo_moodtheme-discogs-effnet-1.onnx|2739322|7d6270acaa5f4bba4b115a0d6849aca05ed6bd153dcb6d9da4f6ab9f99ef10ff|CC BY-NC-SA 4.0；与原ND文本冲突未解决|[固定下载源](https://essentia.upf.edu/models/classification-heads/mtg_jamendo_moodtheme/mtg_jamendo_moodtheme-discogs-effnet-1.onnx)|
|voice|voice_instrumental-discogs-effnet-1.onnx|514114|20155e4c439714b0c45c08644b73c8e12d9dccb173bd4ab9934bf1e5aee837ca|CC BY-NC-SA 4.0；与原ND文本冲突未解决|[固定下载源](https://essentia.upf.edu/models/classification-heads/voice_instrumental/voice_instrumental-discogs-effnet-1.onnx)|
|musicnn|msd-musicnn-1.onnx|3168334|49668ffec47e52e94b96f45930bb46a28a1368d4bdfb5c05378fa834aca616e1|CC BY-NC-SA 4.0；与原ND文本冲突未解决|[固定下载源](https://essentia.upf.edu/models/autotagging/msd/msd-musicnn-1.onnx)|
|deam|deam-msd-musicnn-2.onnx|82032|2cb8f33f188d73fcb651f7c065b049959166c7852f454a59c13e66fe2c092bde|CC BY-NC-SA 4.0；与原ND文本冲突未解决|[固定下载源](https://essentia.upf.edu/models/classification-heads/deam/deam-msd-musicnn-2.onnx)|
|gate|yamnet_3s.onnx|16109405|47363761b27c34fe1f9da8177c40589e9714b422e129f3210be730338f8cf72c|Apache-2.0；保留Google与Rockchip通知|[固定下载源](https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yamnet/yamnet_3s.onnx)|

许可原文及来源：[MTG模型概览](https://essentia.upf.edu/models.html)、[保留的MTG LICENSE](models/LICENSE.txt)、[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en)、[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)、[YAMNet通知](models/LICENSE-YAMNET.txt)、[Rockchip通知](models/LICENSE-RKNN.txt)。

下载命令默认选全部六份；--only gate只选gate。每次下载前列出许可，--check仅校验本地文件、不联网。对已有有效文件跳过下载；坏文件默认保留并报错，显式--repair才在替代文件验证成功后原子替换。

本版按维护者确认的本地非商业用途安排；代码 AGPL、YAMNet Apache 与 MTG 模型条件分别标注，不向 AGPL 代码追加 NC。原权重和元数据均不修改，不发布微调/量化/转换权重，也不进行商业授权推定。

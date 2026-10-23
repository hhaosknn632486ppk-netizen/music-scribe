> 历史记录：本页描述 github-source-2 的安装验收；其中全长延音失败已在 1.3.1 修复，当前结果见 [TIE_FIX_ACCEPTANCE.md](TIE_FIX_ACCEPTANCE.md)。

# 新用户安装与 AI 助手入口验收

日期：2026-10-23，版本 github-source-2。目标是检验别人拿到源码后，能否安装、显式取得模型、运行本地分析并让助手读取证据。没有替换模型或更改音乐分类/转录算法；本地完整版及旧源码包保留。

## 当前可复现路线

| 检查 | 结果 | 范围 |
|---|---|---|
| 轻量环境安装 | 新建隔离 Python 3.12.13 环境，pip check / doctor 通过 | 无 TensorFlow、torch、Basic Pitch、librosa、music21、Verovio |
| 轻量回归 | 44/44，通过，无跳过 | 门控、下载与助手桥接；包含 librosa 对照的 test_semantics 在完整环境运行 |
| 完整环境安装 | 新建隔离 Python 3.10.22 环境，pip check / doctor 通过 | 旧兼容路线，不扩大到 3.12；3.10 已结束上游维护 |
| 完整回归 | 91/91，通过，无跳过 | 原 83 项加 8 项助手桥接契约 |
| 模型与样本 | 在空模型目录重新下载六份模型，逐项 bytes/SHA256 校验通过；公开音频另行下载 | 权重约 40.6 MB，没有放进 Git |
| 默认真实示例 | 音乐与讲话分析、0–8 秒查询、一致性验证全部通过 | 音乐为 music / ambiguous，讲话为 non_music / not_music |
| 可选排谱示例 | --with-score 运行公开音乐前 12 秒，XML/SVG/MIDI 和语义均生成并通过一致性验证 | 135 个逻辑音符区间，缺失/改变为 0，额外/改变为 0；这不是人工真值准确率 |
| 缺模型 | 明确 unavailable，退出码 4，不补造音乐风格 | 不自动下载或调用云端替代 |
| 官方前端复核 | 14 个特征布局/音频案例和 10 个模型输出对照通过 | 验证用途的 Essentia.js 不成为运行依赖；不证明识别准确率 |

前端源码此前只有注释变更，但旧验证记录还绑定旧文件摘要，导致 verify_semantics 拒绝新输出。本轮实际重新运行官方参考，并刷新 FRONTEND_VALIDATION.json；没有删掉或绕过摘要检查。verify_semantics 另增加 --models-dir，避免分析在外部模型目录成功、校验却找错目录。

## 已发现并保留的谱面限制

**同一公开音乐全长生成了 XML/SVG，程序也返回 completed，但 verify_output 检出了未配对或不连续的 tie stop。** 这项全长谱面一致性没有通过，未隐藏为成功，也没有在本次安装文档工作中扩大修改排谱算法。

因此默认新手演示验证语义及讲话拒绝行为；--with-score 明确取前 12 秒，并实际执行两种校验。短片段通过不代表整曲、复杂复调或人工级总谱可靠。助手必须区分程序完成、文件写出、一致性通过、识别正确这四件事。

## 轻量化与测试边界

轻量虚拟环境目录本次约 401 MiB，不含基础 Python、约 40.6 MB 的模型和下载缓存；这是磁盘体积，不是内存占用。首次安装仍要下载 NumPy/SciPy/ORT/codec 等依赖，不能把源码 ZIP 体积当作完整运行体积。

本次在已有 uv 的 Windows x64 主机上从空虚拟环境验证，未模拟全新 Windows 的安装器界面。Linux/macOS/ARM、其他 Python、GPU/分轨、每家助手的 MCP/插件注册及云端 API 均不在本轮验收范围。当前接入方式是有本地命令权限的助手执行 examples/llm_tool.py 并读 JSON；普通网页聊天需用户先运行再粘贴结果。

两份真实音频是已使用过的公开样本，没有新增独立标注真值。模型候选、分数、听感情绪不能当作正确概率或作者意图。模型非商业条件与 SA/ND 冲突未改变。

QUICKSTART.md、INSTALL.md、LLM_INTEGRATION.md 和 examples/assistant_prompt.txt 提供完整命令及解释规则。详细可机器读取的检查范围见 NEW_USER_ACCEPTANCE.json。

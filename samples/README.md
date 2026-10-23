# 可选公开样本引用（不包含录音）

SAMPLES.json只引用三份既有官方librosa示例：Brahms/US Army Strings的公共领域演奏、NPS鲸鸣公共领域录音，以及保留CC BY 4.0来源说明的LibriSpeech讲话。录音本身不在包中；来源、署名、URL和固定SHA逐项保留。许可依据为这些来源说明，不额外为录音权利作担保。

这份公开示例清单不是历史34真实样本的重命名，也不是新的独立准确率验收集。历史私人录音、用户派生谱面、NC测试录音和来源未核实的材料留在本地，不随此候选导出。用户可以提供自己的--manifest扩展评测；缺失/错误均明确记录，不悄悄缩小分母，缺失时返回非零。

```powershell
python fetch_test_samples.py -o 'D:\ExampleAudio'
$env:MUSIC_SCRIBE_MODELS='D:\MusicModels\music_scribe'
python evaluate_samples.py --audio-dir 'D:\ExampleAudio' -o 'D:\Results\new_example_eval' --block-python-network
```

fetch是用户显式联网的工具；分析入口不导入它。evaluate只读本地录音及权重，不下载。目录中没有附带音频、音乐识别结果或任何用户私人材料。

可选validate_frontend_reference.py及tools/reference_frontend.cjs继续支持外部官方Essentia.js数值复核；需用户提供已取得的参考包，不随源码附带Node/WASM或自动下载它。本次主要验收包含原合成fixture及YAMNet参数控制，没有新做TensorFlow逐分数等价或完整外部Node复核。

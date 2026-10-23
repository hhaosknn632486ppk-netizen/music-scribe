# 调用与解释规则

单独语义使用--semantics-only；联合转录使用--semantics。权重在--models-dir或MUSIC_SCRIBE_MODELS指定的本地目录，缺失返回unavailable及显式获取提示，不下载、不用云端替代。

先读summary.json，查看schema、music_presence、global.status、classification_ran、styles.level和warnings。music-semantics/1.1含音乐门控，旧1.0不应被视为有相同保护。

- not_music、uncertain_input、insufficient_evidence、unavailable：不补造音乐风格、情绪或器乐判断；原始声音事件候选不等于音乐结论。
- coarse：仅使用返回的粗类，不从labels词表、NPZ或常识补回被抑制的细标签；有人声/器乐等内容类型不是流派。
- mixed：全局摘要仅汇总检出的音乐时间，不套用于讲话部分。
- fine：仍为模型候选，不代表正确概率或作者意图。

局部query的decision对应请求区间；证据不足时不借整曲风格或被隐藏上下文推断当前讲话。时间以原音频起点为零，窗口并非精确情绪转折标注。

引用输入SHA256、窗口/patch ID以配对证据；指纹不证明录音真实性或音乐判断正确。向在线聊天发送JSON是用户后续的外部发送动作，不属于本地推理。源码获取/使用限制见LICENSE_STATUS.md，不能因为结果可用就宣称所有权重可商用。

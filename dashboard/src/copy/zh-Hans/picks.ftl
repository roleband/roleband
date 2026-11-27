## 首选

## 页面
picks-loading = 正在加载你的首选…
picks-load-failed = 无法加载你的首选
picks-refresh-failed = 无法更新你的首选。显示的是上一次的结果。
picks-fresh-more = 自此列表加载以来，新增了 { $count } 个首选。
picks-host = { $host ->
    [claude-code] Claude Code
    [codex] Codex
   *[other] 你的助手
}

## 空列表
picks-empty-title = 还没有达到你标准的{ -role }
picks-empty-read = { $count ->
   *[other] 本周已阅读 { $count } 个{ -role }。下一个符合条件的会出现在这里。
}
picks-empty-filtered-title = 没有符合这些筛选条件的首选
picks-empty-filtered = { $count ->
   *[other] 筛选条件隐藏了 { $count } 个首选。
}
picks-empty-search-title = 没有符合此搜索的首选

## 列表上方的提示
picks-note-paused = 检查已暂停。恢复之前不会阅读任何内容。
picks-resume = 恢复检查
picks-resume-failed = 无法恢复检查。请重试。
picks-note-asks = { $host } 在每条命令前都会询问，因此检查无法自动运行。
picks-note-fix = 如何解决
picks-note-disconnected = { $host } 已不再连接。
picks-note-connect = 重新连接

## 列表末尾
picks-end-checked = { $host } 于{ $when }检查过。
picks-end-waiting = { $count ->
   *[other] 有 { $count } 个{ -role }在等待。
}
picks-end-stopped = 这次检查提前停止：{ $reason }。其余的在下次检查时读取。
picks-end-stopped-plain = 这次检查未完成就停止了。其余的在下次检查时读取。
picks-end-passed-only = { $passed }。
picks-end-passed = { $count ->
   *[other] 本周略过了 { $count } 个{ -role }
}
picks-end-passed-none = 本周没有略过任何{ -role }。

## 显示“不适合我”：你移除的首选
picks-removed-said = { $reason ->
    [pay_too_low] 你说薪资太低。
    [wrong_level] 你说级别不合适。
    [wrong_role] 你说工作不对口。
    [company] 你说不考虑这家公司。
    [wrong_place] 你说地点不合适。
    [wrong_domain] 你说领域不对。
   *[other] 你说是其他原因。
}
picks-removed-words = 你的原话：“{ $words }”。
picks-removed-put-back = 恢复
picks-removed-put-back-name = 恢复：{ $title }
picks-removed-empty-title = 没有标记为“不适合我”的首选
picks-removed-empty = 你标记为不适合我的首选会连同你的原因保留在这里，以防你改变主意。

## 首选上的“不适合我”：提问
picks-why-title = 为什么不适合你？
picks-why-role = { $title } · { $company }
picks-why-pay = 薪资太低
picks-why-level = 级别不合适
picks-why-work = 工作不对口
picks-why-company = 不考虑这家公司
picks-why-place = 地点不合适
picks-why-other = 其他原因
picks-why-note = 选择一个原因后，该{ -role }会从首选和雷达中移除，并告诉你的助手原因。
picks-why-skip = 不说明原因
picks-why-keep = 保留

## 已略过
picks-passed-heading = 已略过
picks-passed-loading = 正在加载已略过的内容…
picks-passed-load-failed = 无法加载已略过的内容
picks-passed-summary = { $count ->
   *[other] 本周略过了 { $count } 个{ -role }
}
picks-passed-back = 返回首选
picks-passed-close = 差一点（{ $count }）
picks-passed-read = 已阅读并略过（{ $count }）
picks-passed-ruled = 阅读前被硬性规则排除（{ $count }）
picks-passed-show-all = 查看全部 { $count } 个
picks-pass-hard-rule = 违反一条硬性规则
picks-pass-hard-rule-named = 硬性规则：{ $rules }
picks-pass-off-direction = 方向不同
picks-pass-below-level = 低于你的级别
picks-pass-out-of-reach = 难以企及
picks-pass-not-better = 不算更进一步
picks-pass-not-real = 并非在招职位
picks-pass-other = 其他
picks-passed-empty-title = 本周没有略过的{ -role }
picks-passed-empty = 助手阅读后未选中的{ -role }会列在这里，并附上原因。

## 引导：设置之前的首选
picks-onboard-headline = 你的 AI 助手
picks-onboard-line = 前沿 AI 模型了解你想要什么，阅读每一个新{ -role }，只留下少数值得你行动的。
picks-onboard-count = { $count ->
   *[other] 个新{ -role }，每一个都会阅读
}
picks-onboard-reason-work-lead = 你想要的工作
picks-onboard-reason-work = { $lead }，符合你设定的级别。
picks-onboard-reason-more-lead = 比你现在拥有的更多
picks-onboard-reason-more = { $lead }，无论是薪酬还是职责范围。
picks-onboard-step-say = 对你的助手说一句话
picks-onboard-step-arrive = 首选会出现在这里
picks-onboard-say = 在你的助手中说这句话
picks-onboard-works-with = 适用于 Claude Code 和 Codex
picks-onboard-sentence = 运行 `roleband connect --apply`，然后设置我的首选。
picks-onboard-sentence-connected = 设置我的首选
picks-onboard-waiting = 正在等待你的助手
picks-onboard-connected = { $host } 已连接。它保存的内容会显示在这里。
picks-onboard-terminal = 或在终端中运行命令
picks-onboard-footnote = 大约十分钟，使用你现有的套餐。它让你的助手无需询问即可运行 roleband。你的简历和它阅读的{ -role }会发送给你助手所用的模型。
picks-onboard-in-terminal = 在终端中，针对
picks-onboard-terminal-host = 助手
picks-onboard-in-host = 在 { $host } 中
picks-onboard-back = 返回一句话
picks-onboard-access = 让你的助手读取你的{ -role }并保存首选。
picks-onboard-under-way = 设置正在进行
picks-onboard-under-way-line = { $host } 会提问。它保存的内容会显示在这里。
picks-onboard-row = { $step ->
    [connect] { $host } 已连接
    [background] 你的背景
    [situation] 你目前的处境
    [bar] 什么会让你行动
    [rules] 硬性规则
    [tradeoffs] 你愿意如何取舍
    [targets] 想去和想避开的公司
    [calibration] 先看看真实的{ -role }
    [budget] 你希望多久收到一次消息
    [confirm] 复述你在寻找什么
    [trial] 在今天开放的{ -role }上先试一次
   *[routine] 设定每天运行的检查
}
picks-onboard-row-now = { $step ->
    [trial] 正在试运行
    [routine] 正在设置
   *[other] 正在询问
}
picks-onboard-row-waits = 等待首次扫描
picks-onboard-row-saved = 已保存
picks-onboard-resume = 关闭了对话？任何对话都可以继续：

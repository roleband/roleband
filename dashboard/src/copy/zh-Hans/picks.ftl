## 首选

## 页面
picks-loading = 正在加载你的首选…
picks-load-failed = 无法加载你的首选
picks-not-set-up = 首选尚未设置
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
picks-passed-removed = 你移除的（{ $count }）
picks-passed-close = 差一点（{ $count }）
picks-passed-read = 已阅读并略过（{ $count }）
picks-passed-ruled = 阅读前被硬性规则排除（{ $count }）
picks-passed-said = { $reason ->
    [pay_too_low] 你说薪资太低。
    [wrong_level] 你说级别不合适。
    [wrong_role] 你说工作不对口。
    [company] 你说不考虑这家公司。
    [wrong_place] 你说地点不合适。
    [wrong_domain] 你说领域不对。
   *[other] 你说是其他原因。
}
picks-passed-words = 你的原话：“{ $words }”。
picks-passed-put-back = 恢复
picks-passed-put-back-failed = 无法恢复“{ $title }”。请重试。
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

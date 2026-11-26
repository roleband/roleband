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
picks-end-passed = { $count ->
   *[other] 本周略过了 { $count } 个{ -role }。
}

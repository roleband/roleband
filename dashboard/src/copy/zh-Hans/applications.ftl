applications-board-summary = { $moving } 个进行中 · { $decided } 个已决定 · { $closed } 个未通过或已关闭 · { $needNext }

applications-board-need-next = { $count } 个需要设定下一步

applications-board-load-failed = 无法加载求职进展

applications-board-scroll-back = 显示前面的列

applications-board-scroll-on = 显示后面的列

applications-column-decided = 已决定

applications-column-closed = 未通过或已关闭

applications-column-empty-saved = 在你的雷达上保存一个{ -role(num: "one") }，即可从这里开始。

applications-column-empty = 暂无内容。

applications-column-count-of = { $count }/{ $total }

applications-column-no-matches = 没有匹配项。

applications-no-matches = 没有符合这些筛选条件的内容。

applications-empty = 求职进展中暂无内容

applications-empty-hint = 在你的雷达上保存一个{ -role(num: "one") }，即可将它添加到这里。

applications-empty-radar = 打开雷达

applications-column-menu = { $column }列选项

applications-column-hide = 隐藏此列

applications-column-hide-last = 看板上始终保留一列

applications-search-label = 按公司或职位名称搜索求职进展

applications-search-placeholder = 搜索公司或职位名称…

applications-filter-highlight-instead = 改为高亮

applications-filter-reset = 全部重置

applications-filter-remove = 移除筛选条件：{ $filter }

applications-filter-menu = 筛选求职进展

applications-filter-quick = 快速筛选

applications-quick-overdue = 已逾期

applications-quick-due-week = 7 天内到期

applications-quick-needs-next = 待定下一步

applications-quick-quiet = 久无动静

applications-quick-high-priority = 优先级 4+

applications-filter-while = 筛选时

applications-mode-only = 仅显示匹配项

applications-mode-only-hint = 不匹配的项不再显示。

applications-mode-highlight = 高亮匹配项

applications-mode-highlight-hint = 全部保留，不匹配的项变淡。

applications-columns = 列

applications-columns-hidden = 列，已隐藏 { $count } 列

applications-columns-show = 显示列

applications-columns-show-all = 显示全部列

applications-card-actions = 移动或更改 { $title }

applications-card-due-interview = { $offset ->
        [0] 今天面试
        [1] 明天面试
       *[other] { $date } 面试
    }

applications-card-due-step = { $offset ->
        [0] 今天到期
        [1] 明天到期
       *[other] { $date } 到期
    }

applications-card-overdue = 逾期 { $days } 天

applications-card-posting-closed = 招聘信息已关闭

applications-card-comments = { $count } 条评论

applications-card-priority = 优先级 { $priority }/5

applications-card-days-short = { $days } 天

applications-card-days-in-stage = 已在此阶段 { $days } 天

applications-card-quiet = 已在此阶段 { $days } 天，{ $quiet } 天无新动态

applications-card-ended = { $ending }（止于 { $stage }）

applications-menu-label = 移动 { $title }

applications-menu-move-to = 移至

applications-menu-remove = 移出求职进展

applications-moved = 已将 { $title } 移至 { $stage }

applications-moved-hidden = 已将 { $title } 移至 { $stage }。“{ $column }”列已隐藏。

applications-move-undo = 撤销

applications-move-failed = 无法移动 { $title }。请重试。

applications-undo-failed = 无法将 { $title } 移回。请重试。

applications-move-failed-interview-kept = 无法移动 { $title }，但面试已保存。打开该申请即可更改或删除这场面试。

applications-removed = 已将 { $title } 从你的求职进展中移除

applications-remove-failed = 无法移除 { $title }。请重试。

applications-interview-title = 面试在什么时候？

applications-interview-for = { $company } 的 { $title }

applications-interview-pick-day = 选择日期

applications-interview-when-timed = { $date } · { $time }

applications-interview-when-day = { $date } · 时间待定

applications-interview-zone = 时区：{ $zone }

applications-interview-no-time = 时间待定

applications-interview-times = 时间

applications-interview-time-invalid = 请按 { $example } 的格式输入时间。

applications-interview-day-missing = 请选择面试日期。

applications-interview-optional = 可选

applications-interview-round-recruiter = HR 初筛

applications-interview-round-hiring-manager = 用人经理面试

applications-interview-round-technical = 技术面试

applications-interview-round-panel = 多对一面试

applications-interview-round-final = 终面

applications-interview-round = 轮次

applications-interview-round-add = 填写其他轮次名称

applications-interview-round-name = 轮次名称

applications-interview-default-label = 面试

applications-interview-time = 时间

applications-interview-format = 形式

applications-interview-format-video = 视频

applications-interview-format-phone = 电话

applications-interview-format-onsite = 现场

applications-interview-link = 会议链接

applications-interview-link-placeholder = 粘贴会议链接

applications-interview-link-invalid = 请粘贴以 https:// 开头的完整链接。

applications-interview-cancel = 取消

applications-interview-submit = 移至 { $stage }

applications-interview-add-title = 添加面试

applications-interview-edit-title = 编辑面试

applications-interview-edit-submit = 保存面试

applications-interview-delete = 删除面试

applications-interview-outcome = 结果

applications-interview-outcome-none = 暂无

applications-interview-outcome-passed = 已通过

applications-interview-outcome-not-passed = 未通过

applications-interview-outcome-cancelled = 已取消

applications-interview-notes = 备注

applications-interview-failed = 无法保存面试。请重试。

applications-interview-delete-failed = 无法删除面试。请重试。

applications-interview-delete-confirm = 删除这场面试？

applications-tabs-label = 求职进展视图

applications-list-head-next = 下一步

applications-list-head-actions = 操作

applications-list-clear = 没有待开始的事项

applications-list-clear-board = 在看板上查看进行中的职位

applications-list-not-for-me = 不适合我 · { $title }

applications-list-column-left = 左移

applications-list-column-right = 右移

applications-list-columns-reset = 重置列

applications-upnext-overdue = 已逾期

applications-upnext-day = { $offset ->
        [0] 今天
        [1] 明天
       *[other] { $date }
    }

applications-upnext-interview = 面试：{ $label }

applications-upnext-step = 下一步：{ $step }

applications-upnext-step-when = 当天结束前

applications-upnext-empty = 暂无到期事项。为申请设置下一步或添加面试后，就会显示在这里。

applications-month-label = 日历

applications-month-prev = 上个月

applications-month-next = 下个月

applications-month-today = 今天

applications-month-interviews = { $count } 场面试

applications-month-steps = { $count } 项下一步

applications-month-day = { $date }：{ $summary }

applications-month-legend-interview = 面试

applications-month-legend-step = 下一步

applications-month-day-empty = 这天没有安排。

applications-month-failed = 无法加载日历

applications-page-bar = 申请

applications-page-back = 求职进展 / { $view }

applications-page-back-board = 打开看板

applications-page-load-failed = 无法加载这份申请

applications-page-place = { $index } / { $total }

applications-page-previous = 本列上一项：{ $title }

applications-page-next = 本列下一项：{ $title }

applications-page-more = 更多操作

applications-page-more-label = 这份申请的更多操作

applications-page-copy-link = 复制链接

applications-page-withdraw = 撤回

applications-link-copied = 链接已复制

applications-link-copy-failed = 无法复制链接。请从地址栏复制。

applications-stage-button = { $stage } · { $days }

applications-stage-menu-label = 更改 { $title } 的阶段

applications-change-failed = 无法保存对 { $title } 的更改。请重试。

applications-crossing-closed = { $days ->
        [0] 这条招聘信息在你申请当天关闭。
       *[other] 这条招聘信息在你申请 { $days } 天后关闭。
    }

applications-crossing-reopened = { $days ->
        [0] 这条招聘信息在你申请当天重新发布。
       *[other] 这条招聘信息在你申请 { $days } 天后重新发布。
    }

applications-crossing-pay = { $days ->
        [0] 公布的薪酬区间在你申请当天有变动。
       *[other] 公布的薪酬区间在你申请 { $days } 天后有变动。
    }

applications-crossing-dismiss = 忽略

applications-next-title = 下一步

applications-next-interview-none = 尚未安排面试。

applications-next-interview-all-day = { $date }，全天

applications-next-interview-at = { $date } { $time }

applications-next-interview-meta = { $when } · { $format }

applications-next-interview-join = 加入

applications-next-interview-join-label = 加入 { $label }

applications-next-interview-edit = 编辑面试

applications-next-empty = 还没有下一步。

applications-next-set = 设置下一步

applications-next-edit = 编辑下一步

applications-next-done = 标为完成

applications-next-prompt = 下一步是什么？

applications-next-due = 截止日期（可选）

applications-next-required = 请填写下一步，或点击“取消”。

applications-next-save = 保存下一步

applications-notes-title = 备注

applications-notes-add = 添加备注

applications-notes-edit = 编辑备注

applications-notes-empty = 还没有备注。

applications-notes-label = 备注

applications-notes-more = 显示全部

applications-notes-less = 收起

applications-notes-save = 保存备注

applications-feed-title = 动态

applications-feed-mode-label = 显示

applications-feed-mode-comments = 评论

applications-feed-mode-all = 全部动态

applications-feed-empty = 还没有评论或更改。

applications-feed-fold = { $count } 条更新：{ $changes }

applications-feed-added = 已加入求职进展

applications-feed-added-at = 加入时阶段：{ $stage }

applications-feed-moved = 移至 { $stage }

applications-feed-priority = 优先级已更改

applications-feed-notes = 备注已编辑

applications-feed-next-step = 下一步已更改

applications-feed-updated = 已更新

applications-feed-by-agent = 由助手应用操作

applications-comment-label = 评论

applications-comment-placeholder = 记下发生了什么

applications-comment-submit = 发表评论

applications-comment-author-you = 你

applications-comment-author-agent = 助手应用

applications-comment-edited = 已编辑

applications-comment-edit = 编辑评论

applications-comment-delete-label = 删除评论

applications-comment-delete-confirm = 删除这条评论？

applications-comment-delete = 删除

applications-comment-save = 保存

applications-comment-failed = 无法保存你的评论。请重试。

applications-comment-delete-failed = 无法删除这条评论。请重试。

applications-facts-application = 申请

applications-facts-posting = 招聘信息

applications-facts-interviews = 面试

applications-fact-priority = 优先级

applications-fact-days = 在此阶段

applications-fact-days-value = { $days } 天

applications-fact-applied = 申请时间

applications-fact-applied-not = 尚未

applications-fact-starred = 已保存

applications-fact-starred-yes = 是

applications-fact-starred-no = 否

applications-fact-last-activity = 最近动态

applications-fact-status = 状态

applications-fact-status-open = 开放

applications-fact-status-closed = 已关闭

applications-fact-pay = 公布的薪酬区间

applications-fact-pay-none = 未公布

applications-fact-pay-changed = 已变动

applications-fact-level = 级别

applications-fact-location = 地点

applications-fact-location-more = 及另外 { $count } 个

applications-fact-first-seen = 首次发现

applications-fact-listed-for = 已发布

applications-read-posting = 查看招聘信息

applications-interview-add = 添加面试

applications-interview-edit-label = 编辑{ $label }

applications-posting-row = 求职进展

applications-posting-stage = 阶段

applications-posting-since-today = 从今天起

applications-posting-ended = 结束

applications-posting-interview = 面试

applications-posting-next-step = 下一步

applications-posting-no-step = 暂无

applications-posting-history = 历史记录

applications-posting-history-title = 求职进展历史

applications-posting-history-interview = { $label }面试

applications-posting-history-today = 今天

applications-posting-history-now = { $stage }，{ $days } 天

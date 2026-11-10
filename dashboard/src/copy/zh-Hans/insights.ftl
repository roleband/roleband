## insights

## features/statistics/ClustersView.tsx
insights-clusters-view-semantic-groups-built-from-role = 按职位描述的内容将职位归入集群，并以它们共有的技能命名。同一类职位可能分成多个集群。
insights-clusters-view-market-terrain = 各集群的在招职位
insights-clusters-view-group-landscape = 集群图
insights-clusters-view-area-encodes-active-role-volume = 方块越大，在招职位越多。选择一个方块查看其中的职位。
insights-clusters-view-groups = { $count } 个集群
insights-clusters-view-roles = { $family_display } · { $size } 个职位
insights-clusters-view-clear = 清除
insights-clusters-view-and-more-companies = { $count ->
   *[other] 以及另外 { $n } 家公司
}
insights-clusters-view-role-groups = { $count ->
   *[other] { $count } 个集群
}
insights-clusters-view-largest-group = 最大集群：{ $label } · { $size } 个职位
insights-clusters-view-groups-are-built-from-role = 扫描后会根据职位描述生成集群
insights-clusters-view-about-role-groups = 关于集群
insights-clusters-view-groups-tile = 集群
insights-clusters-view-from-role-descriptions = 基于职位描述
insights-clusters-view-roles-grouped = 已归入集群的职位
insights-clusters-view-largest = 最大集群
insights-clusters-view-roles-in-one-group = 个职位在同一集群
insights-clusters-view-with-a-grouped-role = 有职位在集群中
insights-clusters-view-how-to-read-the-cluster = 如何解读集群图
insights-clusters-view-loading = 正在加载集群…
insights-clusters-view-load-failed = 无法加载集群
insights-clusters-view-group-loading = 正在加载此集群…
insights-clusters-view-group-load-failed = 无法加载此分组

## features/statistics/CompTrendChart.tsx
insights-comp-trend-chart-compensation-over-time = 总薪酬变化趋势
insights-comp-trend-chart-median-total-pay = 估算总薪酬中位数{ $series ->
        [single] （含 p25–p75 分布）
       *[several] { "" }
    } · { $period ->
        [all] 全部时间
       *[days] 最近 { $days } 天
    }
insights-comp-trend-chart-history-is-still-accruing-one = 历史数据还不够。扫描几天后，这条线会逐渐完整。
insights-comp-trend-chart-no-comp-history-yet = 暂无薪酬历史。
insights-comp-trend-chart-roles = { $dim } · { $count } 个职位
insights-comp-trend-chart-by-family = 按职能
insights-comp-trend-chart-breakdown = 细分
insights-comp-trend-chart-compensation-percentile-trend = 薪酬百分位趋势
insights-comp-trend-chart-loading = 正在加载薪酬趋势…
insights-comp-trend-chart-load-failed = 无法加载薪酬趋势

## features/statistics/CompensationPanel.tsx
insights-compensation-panel-compensation = 薪酬
insights-compensation-panel-no-open-roles-with-a = 暂无带薪酬估算的在招职位。
insights-compensation-panel-open-roles-now-coverage = { $total_open } 个在招职位中，有 { $with_comp } 个有估算（{ $pct }%）
insights-compensation-panel-estimated-total-compensation-is-imputed = 根据公司、级别和职能估算，并非雇主公布。请将其视为参考，而不是录用报价。
insights-compensation-panel-published-bands = 公布的薪酬区间
insights-compensation-panel-what-employers-actually-print = 公布的薪酬区间
insights-compensation-panel-bands-from-employers = { $bands } 个区间 · { $employers } 个雇主
insights-compensation-panel-estimated-comp-distribution = 估算总薪酬分布
insights-compensation-panel-median-comp-by-level = 各级别估算总薪酬中位数
insights-compensation-panel-top-paying-companies = 薪酬最高的公司
insights-compensation-panel-median-pay-by-discipline = 各职能估算总薪酬中位数
insights-compensation-panel-what-a-skill-adds-at = 同级别下各技能的薪酬
insights-compensation-panel-roles-naming-the-skill-against = 提到该技能的职位，与同一级别和职能的全部职位对比。它反映的是哪些雇主要求该技能，而不是它值多少。
insights-compensation-panel-not-enough-priced-roles-per = 每项技能下有估算的职位还不够多。
insights-compensation-panel-roles = { $count ->
   *[other] { $count } 个职位
}
insights-compensation-panel-groups-of-roles-or-more = 每柱至少 { $min_roles } 个职位
insights-compensation-panel-base-salary-quoted-from-the = 招聘信息中公布的基本工资，不是估算。每条线代表一个公布的区间，无论有多少职位使用它。
insights-compensation-panel-how-compensation-is-estimated = 薪酬如何估算
insights-compensation-panel-coverage = 已估算
insights-compensation-panel-middle-50 = 中间 50%
insights-compensation-panel-top-decile = 前 10%
insights-compensation-panel-range = 跨度
insights-compensation-panel-about-published-salary-bands = 关于公布区间
insights-compensation-panel-how-a-skill-s-pay = 技能薪酬差异如何计算
insights-compensation-panel-median = { $roles } · 中位数 { $p50 }

## features/statistics/Demand.tsx
insights-demand-open-roles-by-company = 各公司在招职位
insights-demand-each-role-counts-once-however = 每个职位只计一次，无论在多少个地点发布。新增指最近 2 天，关闭指今天。
insights-demand-no-open-roles-at-these = 这些公司暂无在招职位。
insights-demand-more-hold = { $share ->
    [none] 另有 { $companies } 有 { $roles }。
   *[known] 另有 { $companies } 有 { $roles }（这些职位的 { $percent }%）。
}
insights-demand-show-all = 显示全部 { $company }
insights-demand-open-roles-by-region = 各地区在招职位
insights-demand-a-role-open-in-several = 在多个地区招聘的职位在每个地区各计一次。只写了地区的职位（如“远程欧洲”）只在该地区计一次，从不计入其下的国家。“远程 ANZ”计入澳大利亚和新西兰。
insights-demand-no-open-roles-yet = 暂无在招职位。
insights-demand-all-of = { $region } 全部
insights-demand-and-more-countries = { $more ->
   *[other] 以及另外 { $more } 个国家
}
insights-demand-name-no-place-we-can = { $role } 未注明具体地点，例如只写了“远程”。
insights-demand-of = { $shown } / { $companies }
insights-demand-hiring-now-today-new-closed = { $company } 正在招聘 · 最近 2 天新增 { $new_today }，今日关闭 { $closed_today }
insights-demand-each-role-once = 每个职位计一次
insights-demand-with-an-open-role = 有在招职位
insights-demand-how-companies-are-counted = 公司如何计数
insights-demand-longest-open-roles = 招聘时间最长的职位
insights-demand-potential-hard-to-fill-signal = 可能难以招到人。
insights-demand-no-data-yet = 暂无数据。
insights-demand-listed-over-a-year-are = 发布超过一年的 { $role } 视为过时，不计入。
insights-demand-reposted-roles = 重新发布的职位
insights-demand-closed-then-reappeared-a-repeated = 关闭后又重新发布。通常说明难以招到人。
insights-demand-none-detected-yet = 暂未发现。
insights-demand-reposted = { $company } · 重新发布 ×{ $repost_count }
insights-demand-updated-but-never-closed = 多次更新但从未关闭
insights-demand-changed-repeatedly-without-a-closure = 多次变更，从未关闭。
insights-demand-updated-times = 更新 { $update_count } 次
insights-demand-about = 关于 { $title }
insights-demand-how-regions-are-counted = 地区如何计数
insights-demand-all-companies-hiring = 所有在招公司
insights-demand-find-a-company = 查找公司

## features/statistics/DisclosurePanel.tsx
insights-disclosure-panel-of-open-roles-have-not = { $open } 个在招职位中，有 { $pending } 个尚未检查是否公布了薪酬区间，因此不计入。
insights-disclosure-panel-pay-transparency = 薪酬透明度
insights-disclosure-panel-who-states-pay = 谁公布了薪酬区间
insights-disclosure-panel-the-share-of-open-roles = 已检查的在招职位中公布薪酬区间的比例。任何区间都计入：基本工资、总薪酬或未说明。
insights-disclosure-panel-of-checked-roles-state-pay = 已检查的 { $checked } 个职位中 { $rate } 公布了薪酬区间
insights-disclosure-panel-no-open-roles-have-been = 暂无在招职位检查过是否公布薪酬区间。
insights-disclosure-panel-history-is-still-accruing-one = 历史数据还不够。扫描几天后，这条线会逐渐完整。
insights-disclosure-panel-over-time = 随时间变化
insights-disclosure-panel-pay-transparency-trend = 薪酬透明度趋势
insights-disclosure-panel-share-of-checked-open-roles = 已检查的在招职位中公布薪酬区间的占比 · { $window }
insights-disclosure-panel-no-pay-transparency-history-yet = 暂无薪酬透明度历史。
insights-disclosure-panel-the-market-line-moves-when = 市场曲线会随新增公司而变化。“相同公司”只跟踪在 { $since } 扫描的 { $companies }。
insights-disclosure-panel-published-band-trend = 公布区间趋势
insights-disclosure-panel-the-median-floor-and-ceiling = 公布的基本工资区间下限和上限的中位数。每个区间只计一次，无论有多少职位使用它。
insights-disclosure-panel-median-published-band = 公布的{ $basis }区间中位数 · { $window }
insights-disclosure-panel-no-published-base-salary-band = 暂未记录公布的基本工资区间。
insights-disclosure-panel-pay-transparency-over-time-covers = 这一趋势涵盖所有职能。
insights-disclosure-panel-how-the-disclosure-rate-is = 薪酬透明度如何计算
insights-disclosure-panel-disclosure-breakdown = 薪酬透明度细分
insights-disclosure-panel-share-of-open-roles-stating = { $group ->
    [company] 公布薪酬区间的在招职位占比（按公司）
   *[level] 公布薪酬区间的在招职位占比（按级别）
}
insights-disclosure-panel-trend-breakdown = 趋势细分
insights-disclosure-panel-share-of-open-roles-stating-over-time = 公布薪酬区间的在招职位占比随时间变化
insights-disclosure-panel-about-the-published-band-trend = 关于公布区间趋势
insights-disclosure-panel-median-published-base-salary-band = 公布的基本工资区间中位数随时间变化
insights-disclosure-panel-trend-loading = 正在加载薪酬透明度趋势…
insights-disclosure-panel-trend-load-failed = 无法加载薪酬透明度趋势
insights-disclosure-panel-band-trend-loading = 正在加载公布区间趋势…
insights-disclosure-panel-band-trend-load-failed = 无法加载公布区间趋势

## features/statistics/OverlapPanel.tsx
insights-overlap-panel-how-alike-their-roles-are = 各公司职位的相似程度
insights-overlap-panel-not-enough-companies-with-skills = 有技能数据的公司不足，无法比较。请选择两家或更多。
insights-overlap-panel-shared-vocabulary = 共同技能
insights-overlap-panel-each-company-is-its-open = 按在招职位提到的技能比较各公司。越少见的技能权重越高。一家公司有 { $min_jobs } 个职位提到某项技能时，该技能才计入。
insights-overlap-panel-comparison = { $companies } × { $companies } 对比
insights-overlap-panel-exact-matrix = 精确矩阵
insights-overlap-panel-cells-show-how-alike-two = 每个单元格给出两家公司的相似度，从 0 到 100。对角线是每家公司的技能数。悬停可查看共同技能。
insights-overlap-panel-companies-picked = { $picker ->
    [default] 在招职位最多
   *[chosen] { $picked } 家公司
}
insights-overlap-panel-pair-names = { $a } 和 { $b }
insights-overlap-panel-no-shared-skills-yet = 暂无共同技能
insights-overlap-panel-most-alike-of = 是 { $companies } 家公司中特色技能最相近的一对（{ $similarity }）
insights-overlap-panel-companies-compared = 已比较 { $companies } 家公司
insights-overlap-panel-closest-pair = 最相近的一对
insights-overlap-panel-median-pair = 中位的一对
insights-overlap-panel-furthest-pair = 差异最大的一对
insights-overlap-panel-how-skill-overlap-is-calculated = 如何计算技能重合度
insights-overlap-panel-cross-company-skill-overlap-matrix = 跨公司技能重合矩阵
insights-overlap-panel-skills-open = { $company } · { $skill_count } 项技能 · { $open } 个在招
insights-overlap-panel-pair-alike = { $listed ->
    [none] { $a } 和 { $b }：相似度 { $percent }%，{ $union } 项技能中共有 { $shared } 项
   *[some] { $a } 和 { $b }：相似度 { $percent }%，{ $union } 项技能中共有 { $shared } 项：{ $skills }
}
insights-overlap-panel-no-shared-skills = { $a } 和 { $b }：无共同技能

## features/statistics/OverviewPanel.tsx
insights-overview-panel-most-named-skills = 最常提到的技能
insights-overview-panel-what-is-pulling-the-market = 需求最大的技能
insights-overview-panel-the-skills-open-roles-name = 技能按提到它的在招职位数排序。
insights-overview-panel-leads-roles = { $display } 领先 · { $job_count } 个职位
insights-overview-panel-largest-groups = 最大的分组
insights-overview-panel-no-groups-built-yet = 尚未构建分组。
insights-overview-panel-open-the-longest = 招聘时间最长的职位
insights-overview-panel-the-roles-advertised-longest-that = 招聘时间最长的职位。它们可能难以招到人，也可能只是一直挂着。发布日期超过一年的不计入。
insights-overview-panel-no-open-roles = 暂无在招职位。
insights-overview-panel-opened-closed = 新增 { $new_count } · 关闭 { $closed_count }
insights-overview-panel-about-the-demand-field = 关于此图表
insights-overview-panel-what-open-the-longest-means = “招聘时间最长”指什么

## features/statistics/PayBands.tsx
insights-pay-bands-each-line-is-one-published = 每条线代表一个公布的区间。带边框的部分是该级别的中位区间。
insights-pay-bands-any-employer = 任意雇主
insights-pay-bands-published-base-salary-bands-by = 各级别公布的基本工资区间
insights-pay-bands-bands-from-employers = { $bands } 个区间 · { $employers } 个雇主
insights-pay-bands-employer-bands = { $published ->
    [none] 无区间
   *[some] { $range } · { $bands } 个区间
}

## features/statistics/SkillsView.tsx
insights-skills-view-a-narrowed-view-ranks-skills = 筛选后：按这些职位提到某项技能的频率与市场相比排序。未筛选：按职位数排序。
insights-skills-view-no-skills-extracted-for-this = 当前选择暂未找到技能。
insights-skills-view-expected-of-the-role = 职位的基本要求
insights-skills-view-process-leadership-and-collaboration-asks = 大多数职位都要求的流程、领导力和协作技能。
insights-skills-view-against-the-market = 与市场对比
insights-skills-view-what-sets-these-roles-apart = 这些职位的独特之处
insights-skills-view-above-the-line-named-more = 线以上：提及多于市场
insights-skills-view-pick-a-company-a-discipline = 选择一家公司或一个职能，将其职位与市场对比。
insights-skills-view-skill = 技能
insights-skills-view-category = 类别
insights-skills-view-share-of-roles = 职位占比
insights-skills-view-lift = 相对市场
insights-skills-view-lead-skill = { $view ->
    [narrowed] { $skill } 最能区分这些职位
   *[market] { $skill } 领先
}
insights-skills-view-of-roles-name-it = { $view ->
    [narrowed] 这些职位中 { $share } 提到它，市场为 { $market_share }
   *[market] { $share } 的职位提到它
}
insights-skills-view-how-skills-are-ranked = 技能如何排序
insights-skills-view-roles = 职位
insights-skills-view-naming-a-skill = 提到某项技能
insights-skills-view-share-or-lift = { $view ->
    [narrowed] 相对市场
   *[market] 占比
}
insights-skills-view-ranked-here = 在此排序
insights-skills-view-expected = 基本要求
insights-skills-view-of-every-role = 所有职位都应具备
insights-skills-view-any-company = 任意公司
insights-skills-view-what-expected-of-the-role = “职位的基本要求”是什么意思
insights-skills-view-skills-order = { $view ->
    [narrowed] 技能，最独特的在前
   *[market] 技能，最常提到的在前
}
insights-skills-view-loading = 正在加载技能…
insights-skills-view-load-failed = 无法加载技能

## features/statistics/StatisticsView.tsx
insights-statistics-view-window = 时间范围
insights-statistics-view-all-time = 全部时间
insights-statistics-view-statistics-sections = 洞察分区
insights-statistics-view-discipline = 职能
insights-statistics-view-advanced-view = 高级视图
insights-statistics-view-advanced-warning-title = 丑话说在前头
insights-statistics-view-advanced-warning-body = 高级视图专为把脚注当乐趣来读的人准备：百分位数、热力图、流向图，以及背后的每一个数字。你随时可以切换回来。
insights-statistics-view-show-me-everything = 全都给我看
insights-statistics-view-keep-it-simple = 保持简单
insights-statistics-view-part-of-advanced-view = 这个标签页属于高级视图。
insights-statistics-view-show-advanced-view = 显示高级视图

## features/statistics/StockTrajectoryPanel.tsx
insights-stock-trajectory-panel-stock-trajectory = 股价走势
insights-stock-trajectory-panel-no-open-roles-at-public = 上市公司暂无带薪酬估算的在招职位。
insights-stock-trajectory-panel-typical-package = { $equity ->
    [measured] 上市公司典型总薪酬 · 股权为实测
    [mixed] 上市公司典型总薪酬 · 股权部分实测
   *[estimated] 上市公司典型总薪酬 · 股权为估算
}
insights-stock-trajectory-panel-stock-moves-re-price-equity = 只有股权随股价变动。职位公布了基本工资区间时，基本工资取该区间，否则为估算。奖金取自职位公告、薪酬数据或公司自己的规则，否则为估算。仅供参考，不是录用报价。
insights-stock-trajectory-panel-stock-price-change = 股价变动
insights-stock-trajectory-panel-reset-to-today = 重置为今天
insights-stock-trajectory-panel-equity-shockwave = 股权影响
insights-stock-trajectory-panel-who-moves-when-the-stock = 股价变动时谁受影响
insights-stock-trajectory-panel-public-companies = { $move ->
    [up] 上市公司 · +{ $pct }%
   *[other] 上市公司 · { $pct }%
}
insights-stock-trajectory-panel-sorted-by-equity-exposure-only = 按股权占比排序。
insights-stock-trajectory-panel-no-open-roles-at-public-yet = 上市公司暂无在招职位。
insights-stock-trajectory-panel-ticker = 股票代码
insights-stock-trajectory-panel-equity = 股权
insights-stock-trajectory-panel-equity-share = 股权占比
insights-stock-trajectory-panel-today = 今天
insights-stock-trajectory-panel-projected = 预测
insights-stock-trajectory-panel-change = 变化
insights-stock-trajectory-panel-no-exposure = 无股权
insights-stock-trajectory-panel-private-companies = 非上市公司
insights-stock-trajectory-panel-pre-ipo-equity-is-illiquid = 未上市公司的股权没有每日股价，因此该情景不会改变其总薪酬。
insights-stock-trajectory-panel-median-tc = 总薪酬中位数
insights-stock-trajectory-panel-median-tc-full = 总薪酬中位数
insights-stock-trajectory-panel-options = 期权
insights-stock-trajectory-panel-no-equity = 无股权
insights-stock-trajectory-panel-cash-election = 现金或股权
insights-stock-trajectory-panel-about-the-source-labels = 每个数字的来源
insights-stock-trajectory-panel-part-source = { $source ->
    [posted] 公布
    [company_rule] 公司规则
    [measured] 实测
    [mixed] 混合
   *[estimated] 估算
}
insights-stock-trajectory-panel-part-source-explained = { $source ->
    [posted] 来自该公司职位公布的区间
    [company_rule] 该公司说明的这部分发放方式
    [measured] 来自该公司该级别的薪酬数据
    [mixed] 该公司各职位之间不同
   *[estimated] 按此级别估算
}
insights-stock-trajectory-panel-no-company-matches = 没有与“{ $query }”匹配的公司。
insights-stock-trajectory-panel-base = 基本工资
insights-stock-trajectory-panel-bonus = 奖金
insights-stock-trajectory-panel-no-bonus = 无奖金
insights-stock-trajectory-panel-vests = { $schedule } 归属
insights-stock-trajectory-panel-choice-companies = 现金或股权，由你选择
insights-stock-trajectory-panel-choice-explained = 在这些公司，每个人自己选择总薪酬中现金和股权各占多少，因此这里不显示构成，股价变动也不会改变这里的数字。
insights-stock-trajectory-panel-left-out = 未计入：{ $count } 个{ -role }没有构成
insights-stock-trajectory-panel-why-left-out = 这些职位为何未计入
insights-stock-trajectory-panel-left-out-reason = { $reason ->
    [not_us_pay] 美国以外
    [level_unplaced] 级别未定位
    [base_only] 基本工资无总额
    [basis_unclear] 区间未说明基础
    [hourly] 时薪
    [monthly] 月薪
    [period_unclear] 周期不明
    [total_compensation] 以总薪酬公布
    [plugin_without_split] 插件无构成
   *[plugin_not_covered] 插件未读
}
insights-stock-trajectory-panel-projected-tc = 预测总薪酬 { $projected }
insights-stock-trajectory-panel-projected-tc-full = 预测总薪酬 { $projected }
insights-stock-trajectory-panel-equity-figure = 总薪酬的 { $share } 是股权
insights-stock-trajectory-panel-how-stock-trajectory-is-projected = 股价走势如何预测
insights-stock-trajectory-panel-median-tc-tile = 总薪酬中位数
insights-stock-trajectory-panel-median-tc-tile-full = 总薪酬中位数
insights-stock-trajectory-panel-at-price-change = { $move ->
    [up] 在 +{ $pct }% 时
   *[other] 在 { $pct }% 时
}
insights-stock-trajectory-panel-vs-today = 相比今天
insights-stock-trajectory-panel-of-tc-at-risk = 占总薪酬（风险部分）
insights-stock-trajectory-panel-of-tc-at-risk-full = 占总薪酬（受影响部分）
insights-stock-trajectory-panel-stock-price-change-percent = 股价变动百分比
insights-stock-trajectory-panel-how-to-read-equity-sensitivity = 如何解读此图表
insights-stock-trajectory-panel-sensitivity-explained = { $move ->
    [flat] 按今天的股价，每根柱表示股价上涨 10% 为典型总薪酬增加的金额。拖动滑块查看不同情景。
   *[other] 显示此情景下典型总薪酬的美元变化。
}
insights-stock-trajectory-panel-scenario = { $move ->
    [flat] 股价每变动 10% · 在上方调整情景
    [up] +{ $pct }% 情景
   *[down] { $pct }% 情景
}
insights-stock-trajectory-panel-about-public-company-projections = 关于上市公司预测
insights-stock-trajectory-panel-paid-in-cash-unaffected-by = 以现金支付：不受股价影响
insights-stock-trajectory-panel-why-private-companies-do-not = 非上市公司为何不变
insights-stock-trajectory-panel-loading = 正在加载股价走势…
insights-stock-trajectory-panel-load-failed = 无法加载股价走势
insights-stock-trajectory-panel-rsus = RSU

## features/statistics/OfferCalculator.tsx
insights-offer-entered = 由你输入，{ $date }
insights-offer-started-from = { $kind ->
    [role] 已按 { $company } 的 { $title } 填入。
   *[company] 已按 { $company } 的中位职位填入。
}
insights-offer-undo = 撤销
insights-offer-clear = 清除录用条件
insights-offer-another-company = 其他公司
insights-offer-listed-label = 上市或非上市
insights-offer-listed = { $listed ->
    [yes] 上市
   *[no] 非上市
}
insights-offer-bonus-rule = { $rule ->
    [none] 这家公司不发年度奖金。
   *[pct_of_base] 这家公司按级别把奖金定为基本工资的一定比例。请输入你录用条件中的比例。
}
insights-offer-equity-type = 股权类型
insights-offer-grant-unit = 授予单位
insights-offer-grant-unit-option = { $unit ->
    [dollars] 美元
   *[shares] 股数
}
insights-offer-price-needs-key = 请输入今天的股价，或在 { $link } 中添加密钥，以用最近收盘价填入。
insights-offer-price-settings = 设置 › 插件 › 股价
insights-offer-price-no-close = { $ticker } 还没有保存的收盘价。请输入今天的股价。
insights-offer-vesting-year = 第 { $year } 年归属百分比
insights-offer-vesting-sum = 这四年归属授予的 { $pct }%。
insights-offer-sign-on = 第 { $year } 年签约奖金
insights-offer-sign-on-bridges = 这家公司在前两年发放签约奖金，以弥补后置的归属安排。
insights-offer-private = 非上市公司的股权在公司上市或进行要约收购之前无法出售。
insights-offer-valuation-unit = 估值形式
insights-offer-valuation-unit-option = { $unit ->
    [per_share] 每股价格
   *[company] 公司估值
}
insights-offer-valuation-grant = { $unit ->
    [per_share] 授予时股价
   *[company] 授予时估值
}
insights-offer-valuation-test = { $unit ->
    [per_share] 测试股价
   *[company] 测试估值
}
insights-offer-share-count = 流通股数
insights-offer-valuation-hint = 请输入你录用条件中的估值，以及想测试的估值，例如最近一轮融资或你自己的预期。
insights-offer-valuation-none = 没有估值时，股权按授予时的估值显示。
insights-offer-move = { $listed ->
    [yes] 股价变动
   *[no] 估值变动
}
insights-offer-move-aria = { $listed ->
    [yes] 你的录用条件的股价变动百分比
   *[no] 你的录用条件的估值变动百分比
}
insights-offer-missing = { $missing ->
    [price] 请输入今天的股价，以便为股票估值。
    [strike] 请输入行权价，以便为期权估值。
    [valuation] 请输入估值，以便为股票估值。
   *[share_count] 请输入流通股数，以便把估值换算成每股价格。
}
insights-offer-year = 年份
insights-offer-year-n = 第 { $year } 年
insights-offer-four-years = 四年合计
insights-offer-sign-on-column = 签约奖金
insights-offer-tc-today = 今天的总薪酬
insights-offer-tc-today-full = 按今天股价的总薪酬
insights-offer-tc-moved = { $move ->
    [up] +{ $pct }% 总薪酬
   *[down] { $pct }% 总薪酬
}
insights-offer-tc-moved-full = { $move ->
    [up] 上涨 { $pct }% 后的总薪酬
   *[down] 下跌 { $pct }% 后的总薪酬
}
insights-offer-drop = 低于第 { $year } 年
insights-offer-start = 以此开始
insights-offer-column = 你的录用条件
insights-offer-at-your-valuation = 按你的估值
insights-offer-at-your-valuation-full = 按你在 { $date } 输入的估值计算的股权
insights-offer-start-title = 录用条件每年能拿多少
insights-offer-start-intro = 几个简短的问题，一次一个。你输入的内容只保存在这台电脑上。
insights-offer-loading = 正在加载你的录用条件
insights-offer-load-failed = 你的录用条件没有加载出来。
insights-offer-save-failed = 你上一个回答没有保存。再回答一次即可保存。
insights-offer-progress = 第 { $n } 题，共 { $total } 题
insights-offer-q-company = 哪家公司给了你录用条件？
insights-offer-q-company-hint = 它通常的股权和奖金规则会自动填入。
insights-offer-pick-company = 选择公司
insights-offer-all-companies = 所有公司
insights-offer-q-base = 基本工资是多少？
insights-offer-q-base-hint = 录用信上的年薪。
insights-offer-per-year = 每年
insights-offer-per-share = 每股
insights-offer-q-stock = { $vehicle ->
    [options] 录用条件里有多少期权？
    [cash] 你选择拿多少股票？
   *[rsu] 录用条件里有多少股票？
}
insights-offer-q-stock-hint = { $vehicle ->
    [options] { $company } 授予股票期权。请输入录用信上的数量。
    [cash] { $company } 允许你在现金和股票之间分配薪酬。请输入四年里的股票部分：变动只影响这一部分。
    [another] 请输入录用信上的授予总额，以美元或股数计。
   *[rsu] { $company } 授予 RSU。请输入录用信上的授予总额。
}
insights-offer-no-stock = { $vehicle ->
    [options] 没有期权
    [cash] 全部现金
   *[rsu] 没有股票
}
insights-offer-q-strike = 行权价是多少？
insights-offer-q-strike-hint = 你买入每份期权时每股要付的价格。
insights-offer-q-price = { $quote ->
    [yes] 使用 { $company } 的最近收盘价？
   *[no] 今天的股价是多少？
}
insights-offer-q-price-quote = { $date } 收盘时每股 { $price }。
insights-offer-use-price = 使用 { $price }
insights-offer-own-price = 输入价格
insights-offer-q-valuation = { $company } 值多少？
insights-offer-dont-know = 不知道
insights-offer-q-vesting-stated = 你的授予是按 { $schedule } 归属吗？
insights-offer-q-vesting-stated-hint = 这是 { $company } 通常公布的归属安排，按每年占授予的百分比计。
insights-offer-q-vesting = 授予如何归属？
insights-offer-q-vesting-hint = { $named ->
    [yes] { $company } 没有说明。大多数授予在四年内均匀归属。
   *[no] 大多数授予在四年内均匀归属。
}
insights-offer-percent-of-grant = 每年归属授予的百分比。
insights-offer-vesting-yes = 一样
insights-offer-vesting-differs = 我的不同
insights-offer-vesting-other = 其他
insights-offer-vesting-even = 均匀
insights-offer-vesting-too-much = 各年合计为 { $pct }%。请保持在 100% 或以下。
insights-offer-q-bonus = 有年度目标奖金吗？
insights-offer-q-bonus-hint = 按录用信写明的基本工资比例。
insights-offer-bonus-choice = { $pct ->
    [0] 没有奖金
   *[other] { $pct }%
}
insights-offer-bonus-other = 其他目标奖金，占基本工资的百分比
insights-offer-q-sign-on = 有签约奖金吗？
insights-offer-q-sign-on-hint = 入职时的一次性付款，有时分两年发放。
insights-offer-sign-on-yes = 有
insights-offer-sign-on-no = 没有
insights-offer-need = { $what ->
    [company] 请选择一家公司。
    [base] 请输入年基本工资。
    [stock] 请输入金额，或选择旁边的按钮。
    [strike] 请输入行权价。
    [price] 请输入今天的股价。
    [valuation] 请输入授予时的价值，或选择不知道。
    [vesting] 请至少输入一年的归属百分比。
    [bonus] 请选择目标奖金。
   *[sign_on] 请至少输入一笔签约奖金。
}
insights-offer-next = 下一步
insights-offer-done = 完成
insights-offer-back = 返回
insights-offer-cancel = 取消
insights-offer-later = 稍后完成
insights-offer-finished-title = { $named ->
    [yes] 你的 { $company } 录用条件，逐年来看
   *[no] 你的录用条件，逐年来看
}
insights-offer-unfinished = 已回答 { $answered } 题，共 { $total } 题
insights-offer-continue = 继续
insights-offer-typical = 这些是典型数字。换成你自己的，就能看到你的录用条件。
insights-offer-swap = 用我的数字
insights-offer-tag = { $tag ->
    [typical] 典型
    [rule] 公司规则
    [employer] 公司公布
    [estimated] 估算
    [assumed] 假定
   *[quote] 最近收盘价
}
insights-offer-chip-edit = 修改 { $answer }
insights-offer-chip-base = 基本工资 { $amount }
insights-offer-chip-stock = { $kind ->
    [none] 没有股票
    [cash] { $amount } 选为股票
    [options] { $count } 份期权
    [shares] { $count } 股
   *[dollars] { $amount } 股票
}
insights-offer-chip-strike = 行权价 { $amount }
insights-offer-chip-price = 每股 { $amount }
insights-offer-chip-valuation = { $kind ->
    [none] 按授予时价值
    [per_share] 每股 { $from } 到 { $to }
   *[company] 估值 { $from } 到 { $to }
}
insights-offer-chip-vesting = 归属 { $schedule }
insights-offer-chip-bonus = { $pct ->
    [0] 没有奖金
   *[other] { $pct }% 奖金
}
insights-offer-chip-sign-on = { $kind ->
    [none] 没有签约奖金
   *[some] 签约奖金 { $first } + { $second }
}
insights-offer-chart = 每年的总薪酬
insights-offer-vs-today = { $sign ->
    [up] 比按今天股价多 { $amount }
    [down] 比按今天股价少 { $amount }
   *[same] 按今天股价
}
insights-offer-show-table = 查看表格

## features/statistics/TrendsPanel.tsx
insights-trends-panel-demand-history = 需求历史
insights-trends-panel-skill-demand-over-time = 技能需求变化趋势
insights-trends-panel-each-skill-s-share-of = 各技能当天提及占比 · { $window }
insights-trends-panel-top-plotted-in-ledger = 图中显示前 { $plotted } 项 · 列表共 { $total } 项
insights-trends-panel-history-is-still-accruing-one = 历史数据还不够。扫描几天后，这些线会逐渐完整。
insights-trends-panel-no-skill-history-yet = 暂无技能历史。
insights-trends-panel-what-is-measured-changed-on = 统计的公司或技能在 { $dates } 发生了变化，因此图表显示的是占比，而不是数量。
insights-trends-panel-current-ledger = 当前列表
insights-trends-panel-now = 现在
insights-trends-panel-skill-leads = { $skill } 领先
insights-trends-panel-nothing-to-plot-yet = 暂无可绘制的数据
insights-trends-panel-leader-share-line = 最近一天提及占比 { $current_share } · 历史 { $days } 天 · { $window }
insights-trends-panel-history-accrues-one-day-per = 每次扫描积累一天历史 · { $window }
insights-trends-panel-leader-s-share = 领先者占比
insights-trends-panel-of-skill-mentions = 的技能提及
insights-trends-panel-in-the-ledger = 在列表中
insights-trends-panel-history = 历史
insights-trends-panel-days = { $count ->
   *[other] 天
}
insights-trends-panel-latest-day = 最近一天
insights-trends-panel-none-yet = 暂无
insights-trends-panel-of-the-series = 历史数据中
insights-trends-panel-of-skill-mentions-open-roles = 提及占比 { $current_share }，{ $current } 个在招职位
insights-trends-panel-change-points = 变化 { $share_delta } 个百分点
insights-trends-panel-loading = 正在加载技能趋势…
insights-trends-panel-load-failed = 无法加载技能趋势

## features/statistics/VelocityPanel.tsx
insights-velocity-panel-market-current = 按公司
insights-velocity-panel-hiring-flow = 招聘流动
insights-velocity-panel-closures-pull-left-openings-push = 关闭向左，新增向右；菱形表示更新压力。
insights-velocity-panel-net = { $direction ->
    [up] 净增 +{ $net } { $window }
   *[down] 净增 { $net } { $window }
}
insights-velocity-panel-companies = 公司 · { $window }
insights-velocity-panel-open = 在招
insights-velocity-panel-opened = 新增
insights-velocity-panel-time-posted = 发布时长
insights-velocity-panel-from-the-first-scan-that = 招聘信息从首次发现到下线持续的天数。下线原因有多种：已招到、暂停或过期。
insights-velocity-panel-age-of-open-roles = 在招职位的发布时长
insights-velocity-panel-how-long-postings-stay-up = 招聘信息在线多久
insights-velocity-panel-this-builds-up-as-roles = 随着职位关闭逐渐完整。目前只有 { $closed_sample } 个已关闭。
insights-velocity-panel-median-age = 发布时长中位数 { $median_days_open }
insights-velocity-panel-median-time-posted = 在线时长中位数 { $median_observed_listing_duration_days }
insights-velocity-panel-more-already-listed-when-their = 另有 { $first_scan } 个在公司首次扫描时已发布
insights-velocity-panel-net-flow = 净流动
insights-velocity-panel-opened-closed = 新增 − 关闭
insights-velocity-panel-how-to-read-hiring-flow = 如何解读招聘流动
insights-velocity-panel-what-time-posted-measures = “发布时长”衡量的是什么

## features/statistics/ageCopy.ts
insights-age-copy-listed-today = 今天发布
insights-age-copy-listed-for = 已发布 { $days }
insights-age-copy-dated-by-the-employer = { $percent }% 由雇主注明日期
insights-age-copy-counted-from-when-each-role = 自各职位首次发布起算 · { $dated }

## features/statistics/charts/StatisticsCharts.tsx
insights-statistics-charts-skill-open-roles = { $job_count } 个在招职位 · { $category }
insights-statistics-charts-market-demand-field = 需求最大的技能
insights-statistics-charts-company-open-roles = { $open } 个在招职位
insights-statistics-charts-new-closed-today = 最近 2 天 { $new_roles } · 今日 { $closed_roles }
insights-statistics-charts-new-count = 新增 +{ $fresh }
insights-statistics-charts-closed-count = 关闭 −{ $closed }
insights-statistics-charts-open-roles-by-company = 各公司在招职位
insights-statistics-charts-open-new-closed = { $label }：在招 { $open }，新增 { $fresh }，关闭 { $closed }
insights-statistics-charts-closed = 关闭 ←
insights-statistics-charts-opened = → 新增
insights-statistics-charts-hiring-flow-by-company = 各公司招聘流动
insights-statistics-charts-opened-closed-updated = { $company }：新增 { $opened }，关闭 { $closed }，更新 { $updated }
insights-statistics-charts-equity-change = { $direction ->
    [flat] 变化 $0
    [down] −{ $amount }
   *[up] +{ $amount }
}
insights-statistics-charts-no-change = 无变化
insights-statistics-charts-equity-shockwave-by-company = 各公司股权影响
insights-statistics-charts-share-against-market = 这些职位的 { $share }% · 市场的 { $market_share }%
insights-statistics-charts-lift-the-market-s-rate = 市场比例的 ×{ $lift }
insights-statistics-charts-share-of-these-roles = 这些职位中的占比 →
insights-statistics-charts-the-market-s-rate = × 市场比例 →
insights-statistics-charts-what-sets-these-roles-apart = 这些职位的独特之处
insights-statistics-charts-of-these-roles-the-market = { $skill }：这些职位的 { $share }%，市场的 ×{ $lift }
insights-statistics-charts-set-changed = 统计口径变化
insights-statistics-charts-skill-demand-trends = 技能需求趋势
insights-statistics-charts-skill-mentions-change = { $direction ->
    [up] { $skill }：占提及的 { $share }%，+{ $points } 个百分点
   *[down] { $skill }：占提及的 { $share }%，{ $points } 个百分点
}
insights-statistics-charts-skill-mentions-share = { $skill }：占提及的 { $share }%
insights-statistics-charts-pair-alike = 相似度 { $similarity }% · { $shared } 项共同技能
insights-statistics-charts-pair = { $a } × { $b }
insights-statistics-charts-more-alike = 更相似
insights-statistics-charts-less-alike = 不太相似
insights-statistics-charts-cross-company-skill-overlap-heatmap = 跨公司技能重合热力图
insights-statistics-charts-pair-similarity = { $a } 和 { $b }：{ $percent }%
insights-statistics-charts-cluster-roles = { $size } 个职位 · { $family }
insights-statistics-charts-role-cluster-landscape = 分组全景
insights-statistics-charts-roles = { $label }：{ $size } 个职位

## features/statistics/charts/compBands.ts
insights-comp-bands-level-summary = { $label }：{ $bands } 个区间，来自 { $employers } 个雇主，中位数 { $low } 至 { $high }。
insights-comp-bands-1-more-role-states-a = 另有 1 个职位公布了区间，但从未说明是否包含奖金或股权，因此未显示。
insights-comp-bands-more-roles-state-a-range = 另有 { $unclear } 个职位公布了区间，但从未说明是否包含奖金或股权，因此未显示。
insights-comp-bands-1-more-role-states-base = 另有 1 个职位以其他货币或按小时、按月公布基本工资，因此不在此年薪美元刻度上。
insights-comp-bands-more-roles-state-base-pay = 另有 { $elsewhere } 个职位以其他货币或按小时、按月公布基本工资，因此不在此年薪美元刻度上。

## features/statistics/charts/disclosure.ts
insights-disclosure-unclassified = 级别未知
insights-disclosure-no-open-roles-have-been = 暂无在招职位检查过是否公布薪酬区间。
insights-disclosure-share-of-checked-open-roles = 已检查的在招职位中，公布薪酬区间的占比。{ $rates }。{ $unrated ->
        [0] { "" }
       *[other] 另有 { $unrated } 个组尚无已检查的职位，因此无法给出比例。
    }
insights-disclosure-of-roles = { $label }：{ $rate }，{ $checked } 个职位中 { $disclosed } 个
insights-disclosure-rate-states-pay = { $rate } 公布了薪酬区间
insights-disclosure-of-checked-open-roles = 已检查的 { $checked } 个在招职位中 { $disclosed } 个
insights-disclosure-no-pay-transparency-history-recorded = 暂未记录薪酬透明度历史。
insights-disclosure-no-roles-checked-yet = { $dim }：尚无已检查的职位
insights-disclosure-of-checked-roles-state-pay = { $series }：已检查的 { $checked } 个职位中 { $pct } 公布了薪酬区间{ $readings ->
        [single] { "" }
       *[several] （起初为 { $from }）
    }
insights-disclosure-share-of-open-roles-stating = 按{ $dim ->
        [company] 公司
        [level] 级别
       *[overall] 市场
    }统计的公布薪酬区间的在招职位占比，{ $span ->
        [day] 在 { $first }
       *[range] 从 { $first } 到 { $last }
    }。{ $lines }。
insights-disclosure-not-checked = 未检查
insights-disclosure-rate-percent = { $rate }%
insights-disclosure-no-published-pay-band-has = 暂未记录公布的薪酬区间。
insights-disclosure-median-published-salary-band-across = 公布的{ $basis }区间中位数，基于 { $bands } 个不同区间，涵盖 { $roles } 个在招职位：{ $low_p50 } 至 { $high_p50 }。{ $readings ->
        [single] { "" }
       *[several] 起初为 { $start_low } 至 { $start_high }。
    }每个不同区间计一次，而不是每个职位。
insights-disclosure-median-ceiling = 上限中位数
insights-disclosure-median-floor = 下限中位数
insights-disclosure-no-band-posted = 未公布区间

## features/statistics/charts/StatisticsCharts.tsx (by hand)
insights-statistics-charts-more-signals = +{ $count } 个信号
insights-statistics-charts-cluster-size = { $size } 个职位

## features/statistics/CompensationPanel.tsx
insights-compensation-panel-median-pay = 中位数 { $p50 }
insights-compensation-panel-priced-roles = { $with_comp } 个职位
insights-compensation-panel-loading = 正在加载薪酬…
insights-compensation-panel-load-failed = 无法加载薪酬
insights-compensation-panel-min-max = 最低–最高

## features/statistics/Demand.tsx
insights-demand-open = { $role } 在招
insights-demand-loading = 正在加载招聘动态…
insights-demand-load-failed = 无法加载招聘动态
insights-demand-today = 今天
insights-demand-last-2-days = 最近 2 天

## features/statistics/OverlapPanel.tsx
insights-overlap-panel-skills = { $skill_count } 项技能
insights-overlap-panel-loading = 正在加载技能重合度…
insights-overlap-panel-load-failed = 无法加载技能重合度
insights-overlap-panel-compared = 已比较
insights-overlap-panel-alike = 相似

## features/statistics/OverviewPanel.tsx
insights-overview-panel-companies = { $companies } 家公司
insights-overview-panel-loading = 正在加载概览…
insights-overview-panel-load-failed = 无法加载概览

## features/statistics/VelocityPanel.tsx
insights-velocity-panel-opened-count = 新增 { $opened }
insights-velocity-panel-open-count = 在招 { $open_total }
insights-velocity-panel-loading = 正在加载招聘节奏…
insights-velocity-panel-load-failed = 无法加载招聘节奏

## features/statistics/charts/compBands.ts
insights-comp-bands-to = { $low } 至 { $high }
insights-comp-bands-employer-at-level = { $published ->
    [none] { $summary }{ $employer } 在此级别未公布区间。
   *[some] { $summary }{ $employer }：{ $ranges }。
}

## features/statistics/charts/disclosure.ts

## features/statistics/charts/StatisticsCharts.tsx
insights-statistics-charts-overlap-cell = { $cell ->
    [self] { $skillCount }{ "\u000A" }项技能
    [pair] { $similarity }%
   *[empty] { "" }
}

## 洞察中公司划分的两侧
insights-your-companies = 你的公司
insights-other-companies = 其他公司
insights-period-days = { $days } 天

## Insights 多个面板共用的词
insights-common-companies = 公司
insights-common-company = 公司
insights-common-open-roles = 在招职位
insights-common-open-roles-unit = 个在招职位
insights-common-new = 新增
insights-common-closed = 已关闭
insights-common-updated = 已更新
insights-common-skills = 技能
insights-common-market = 市场
insights-common-by-level = 按级别
insights-common-by-company = 按公司
insights-common-all-companies = 所有公司
insights-common-distinct-skills = { $count } 项不同技能
insights-common-last-days-or-all-time = { $period ->
    [all] 全部时间
   *[days] 最近 { $days } 天
}
insights-common-last-days-or-all-history = { $period ->
    [all] 全部时间
   *[days] 最近 { $days } 天
}

## 技能类别
insights-skill-language = 编程语言
insights-skill-framework = 框架
insights-skill-cloud = 云
insights-skill-data = 数据
insights-skill-ml-ai = 机器学习 / AI
insights-skill-infra = 基础设施
insights-skill-security = 安全
insights-skill-process = 流程
insights-skill-leadership = 领导力
insights-skill-collaboration = 协作
insights-skill-industry = 行业

## 统计名称：无名称的分组、同一批公司序列和固定发布时长区间
insights-cluster-unlabeled = 未命名分组
insights-series-same-companies = 相同公司
insights-aging-from-0-days = < 1 周
insights-aging-from-7-days = 1–2 周
insights-aging-from-14-days = 2–4 周
insights-aging-from-30-days = 1–2 个月
insights-aging-from-60-days = 2–3 个月
insights-aging-from-90-days = 3 个月以上

## 概览的一行摘要
insights-brief-open = { $companies } 家公司共有 { $open } 个在招职位。
insights-brief-opened = { $allTime ->
    [yes] 累计新增 { $opened } 个，关闭 { $closed } 个。
   *[no] { $days } 天内新增 { $opened } 个，关闭 { $closed } 个。
}
insights-brief-top-skill = 最热门技能：{ $skill }（{ $count } 个职位）。
insights-brief-largest-group = 最大分组：{ $group }（{ $size } 个职位）。
insights-comp-trend-chart-reference-changed = { $count ->
   *[other] 虚线标出薪酬估算一起变化的时间：这是数据的变化，而不是市场的变化。
}
insights-comp-trend-chart-reference-marker = 薪酬估算于 { $date } 变化
insights-compensation-panel-spread = p25–p75：{ $low }–{ $high } · { $roles }
insights-compensation-panel-estimated-base-by-level = 各级别的估算基本工资
insights-compensation-panel-base-only = 仅基本工资
insights-compensation-panel-base-only-lead =
    { $count ->
       *[other] 另有 { $count } 个职位只有基本工资估算，因此不在上面的数字中。
    }

insights-levels-loading = 正在加载职级表…

insights-levels-load-failed = 无法加载职级表

insights-levels-figure = 各公司如何命名级别

insights-levels-figure-translating = { $company } 的 { $code } 相当于 { $level }

insights-levels-line = 选择任意级别，查看每家有职级表的公司如何称呼它。

insights-levels-line-translating = 高亮列是其他每家公司的同一级别。

insights-levels-kpi-guided = 有职级表

insights-levels-kpi-flat = 职位名称不含级别

insights-levels-kpi-flat-sub = 从未注明级别

insights-levels-kpi-skipped = 无 { $level } 级别

insights-levels-kpi-skipped-sub = 以最接近的级别代替

insights-levels-search = 公司或级别

insights-levels-search-example = Google 或 ICT4

insights-levels-sector = 行业

insights-levels-your-level = { $level }（你的级别）

insights-levels-your-aim = { $level }（你的目标）

insights-levels-translating-column = { $level }（换算中）

insights-levels-translate-from = 以 { $company } { $code } 为基准换算

insights-levels-translating = 正在将 { $company } { $code }（{ $level }）换算到每家公司

insights-levels-clear = 清除

insights-levels-ambiguous = { $count ->
    [1] { $code } 是 { $count } 家公司的级别。选择它作为换算基准。
   *[other] { $code } 在 { $count } 家公司分别代表不同级别。选择一家作为换算基准。
}

insights-levels-engineering = 工程师级别

insights-levels-engineering-title = 这家公司只列出工程师的级别

insights-levels-flat = 此处职位名称不注明级别

insights-levels-flat-title = 除这些级别外，这家公司的职位名称不注明级别

insights-levels-skipped = { $company } 没有 { $level } 级别

insights-levels-skipped-closest = 无 { $level } 级别。最接近：{ $code }

insights-levels-no-guide = 暂无 { $company } 的职级表。

insights-levels-same-as = 与 { $company } 使用相同的级别。

insights-levels-followed-without-guide = 你关注的公司中有 { $count } 家暂无职级表。

insights-levels-empty = 没有匹配的公司或级别

insights-levels-reset = 全部重置

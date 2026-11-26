## Desktop banners. Existing wording moved verbatim; editorial review pending.
# kind=status
banner-db-down = RoleBand couldn't reach its database and is restarting it.
# kind=status
banner-api-down = RoleBand's background service stopped responding and is restarting.
# kind=status
banner-stuck-runs = Cleared scans that had stalled
# kind=status
banner-stale-data = Your radar is out of date, so a scan is queued.
# kind=status
banner-derivations-stale = Some role details are out of date. The next scan updates them.
# kind=status
banner-backup-stale = No recent backup of your data. Nothing is lost. A backup runs every morning.
# kind=status
banner-daily-failed = The scan you started finished with errors. Its output is in the terminal that ran it.
# kind=heading
banner-matching-title = Ranking updated
# kind=sentence
banner-matching-body = Best fit is up to date for every role on your radar.
# kind=heading note="A desktop banner's title: the person's assistant picked $count roles in one go"
banner-top-pick-title = { $count ->
    [one] New top pick
   *[other] { $count } new top picks
}
# kind=status note="Under the title: the first of the picks, its title and company"
banner-top-pick-body = { $title } at { $company }
# kind=heading note="A desktop banner's title: how the Top picks checks fell behind"
banner-picks-stalled = { $reason ->
    [late] Top picks checks are late
    [stopped] A top picks check stopped early
   *[never] No top picks check has run yet
}
# kind=sentence note="Under the title: $count is how many roles wait for the checks"
banner-picks-waiting = { $count ->
    [one] { $count } role is waiting to be read.
   *[other] { $count } roles are waiting to be read.
}

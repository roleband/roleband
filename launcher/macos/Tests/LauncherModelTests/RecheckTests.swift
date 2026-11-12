import Darwin
import Foundation
import Testing
@testable import LauncherCore
@testable import RoleBandLauncher

/// Decisions handed out in order; the last one repeats.
@MainActor
private final class Decisions {
    private var queue: [LaunchMode]
    private(set) var made = 0
    init(_ queue: [LaunchMode]) { self.queue = queue }
    func next() -> LaunchMode {
        made += 1
        return queue.count > 1 ? queue.removeFirst() : queue[0]
    }
}

@MainActor
@Test func aBlockedLaunchReopensOnceTheOtherProgramLetsGoOfTheDatabase() async {
    let decisions = Decisions([.databaseInUse, .databaseInUse, .owned(leftover: nil)])
    var reopened = 0
    let recheck = LaunchRecheck(interval: .milliseconds(1), decide: { decisions.next() }, reopen: { reopened += 1; return true })
    await recheck.watch(.databaseInUse).value
    #expect(decisions.made == 3, "it looks again until the decision changes, then stops looking")
    #expect(reopened == 1)
}

@MainActor
@Test func aReopenThatFailsKeepsTheBlockedLaunchWatching() async {
    let decisions = Decisions([.owned(leftover: nil)])
    var reopened = 0
    let recheck = LaunchRecheck(interval: .milliseconds(1), decide: { decisions.next() },
                                reopen: { reopened += 1; return reopened >= 3 })
    await recheck.watch(.databaseInUse).value
    #expect(reopened == 3, "a copy that could not open is tried again at the next look")
}

@MainActor
@Test func aBlockedLaunchStaysWhileTheDatabaseIsStillInUse() async throws {
    let decisions = Decisions([.databaseInUse])
    var reopened = 0
    let recheck = LaunchRecheck(interval: .milliseconds(1), decide: { decisions.next() }, reopen: { reopened += 1; return true })
    let watching = recheck.watch(.databaseInUse)
    let deadline = ProcessInfo.processInfo.systemUptime + 5
    while decisions.made < 5, ProcessInfo.processInfo.systemUptime < deadline { try await Task.sleep(for: .milliseconds(1)) }
    #expect(decisions.made >= 5, "the watch kept looking while the decision stayed the same")
    watching.cancel()
    await watching.value
    #expect(reopened == 0)
}

@MainActor
@Test func tryAgainMakesTheStartupDecisionAgain() {
    // The app's own database, served by another program while the app attached: Try again opens a
    // fresh copy that starts as the new decision says, instead of reading the old target again.
    var decided: LaunchMode = .databaseInUse
    var reopened = 0
    var asked = 0
    let attached = LauncherModel(mode: .attach, decideMode: { asked += 1; return decided }, reopen: { reopened += 1 })
    defer { attached.stop() }
    attached.retry()
    #expect(asked == 1 && reopened == 1)
    #expect(!attached.checking, "a reopened app reads nothing here")

    // A source install that is still there keeps its session, and Try again reads its status.
    decided = .attach
    attached.retry()
    #expect(asked == 2 && reopened == 1)
    #expect(attached.checking)

    // An owned engine decides again in its own Restart; its leftover server differs every time.
    let owned = LauncherModel(mode: .owned(leftover: nil), decideMode: { asked += 1; return .owned(leftover: 42) },
                              reopen: { reopened += 1 })
    defer { owned.stop() }
    owned.retry()
    #expect(asked == 2 && reopened == 1)
}

@MainActor
@Test func aReopenStartsTheHelperBeforeItQuitsAndQuitsOnlyIfTheHelperStarted() {
    var spawned: [(URL, [String])] = []
    var quits = 0
    let executable = URL(fileURLWithPath: "/Applications/RoleBand.app/Contents/MacOS/RoleBandLauncher")
    var helpersAtQuit: [Int] = []
    let requested = AppReopen.request(spawn: { spawned.append(($0, $1)) }, executable: executable, quit: {
        helpersAtQuit.append(spawned.count)
        quits += 1
    })
    #expect(requested && quits == 1)
    #expect(helpersAtQuit == [1], "the helper is running before this copy quits")
    #expect(spawned.first?.0 == executable && spawned.first?.1 == [AppReopen.argument, String(getpid())])

    struct Refused: Error {}
    #expect(!AppReopen.request(spawn: { _, _ in throw Refused() }, executable: executable, quit: { quits += 1 }))
    #expect(quits == 1, "without a helper, this copy stays open and keeps watching")
}

@Test func theHelperOpensTheAppOnlyOnceThePreviousCopyHasQuit() async {
    var clock: TimeInterval = 0
    var pauses = 0
    let pause = { pauses += 1; clock += 1 }
    var opened = 0
    var looks = 0
    let quitsAfterTwoLooks = await AppReopen.reopen(after: 4242, alive: { _ in looks += 1; return looks < 3 },
                                                    now: { clock }, pause: pause, open: { opened += 1 })
    #expect(quitsAfterTwoLooks && opened == 1, "it opens the app once the previous copy is gone")

    pauses = 0
    let neverQuits = await AppReopen.reopen(after: 4242, limit: 10, alive: { _ in true }, now: { clock }, pause: pause,
                                            open: { opened += 1 })
    #expect(!neverQuits && pauses == 10 && opened == 1, "a copy still running after the limit keeps its place")

    struct Refused: Error {}
    let refused = await AppReopen.reopen(after: 4242, alive: { _ in false }, now: { clock }, pause: pause,
                                         open: { throw Refused() })
    #expect(!refused)

    let itself = await AppReopen.reopen(after: getpid(), alive: { _ in false }, now: { clock }, pause: pause,
                                        open: { opened += 1 })
    #expect(!itself && opened == 1, "a helper never waits for itself")
}

import Foundation
import LauncherCore
import Testing
@testable import RoleBandLauncher

/// An owned engine whose port another program can hold, recording what the model asks of it.
private actor PortBoundary {
    var calls: [String] = []
    var current = OwnedEngineSnapshot(state: .stopped)
    var installation: Installation
    init(_ installation: Installation) { self.installation = installation }
    /// Ports another program takes while the engine stops, so its start there is refused.
    var takenOnStart: Set<Int> = []
    func takeOnStart(_ port: Int) { takenOnStart.insert(port) }
    /// A refusal the engine's next start meets that has nothing to do with its port.
    var refusal: HostProblem?
    func refuseStart(_ problem: HostProblem) { refusal = problem }
    func start() throws {
        calls.append("start")
        if let refusal {
            self.refusal = nil
            current = OwnedEngineSnapshot(state: .needsAttention, problem: refusal)
            throw refusal
        }
        if let port = URL(string: installation.apiOrigin)?.port, takenOnStart.contains(port) {
            current = OwnedEngineSnapshot(state: .needsAttention, problem: .portInUse,
                                          portConflict: PortConflict(port: port, holder: nil, suggestion: nil))
            throw HostProblem.portInUse
        }
        current = OwnedEngineSnapshot(state: .running)
    }
    func stop() { calls.append("stop"); current = OwnedEngineSnapshot(state: .stopped) }
    func use(_ port: Int) throws -> Installation {
        calls.append("use \(port)")
        installation = try installation.on(port: port)
        return installation
    }
    func hold(by holder: String?, suggestion: Int?) {
        current = OwnedEngineSnapshot(state: .needsAttention, problem: .portInUse,
                                      portConflict: PortConflict(port: 8010, holder: holder, suggestion: suggestion))
    }
    func snapshot() -> OwnedEngineSnapshot { current }
    nonisolated var service: OwnedEngineService {
        OwnedEngineService(start: { try await self.start() }, restart: { try await self.start() },
                           stop: { await self.stop() }, snapshot: { await self.snapshot() },
                           use: { try await self.use($0) })
    }
}

private func ownedInstallation() throws -> Installation {
    try JSONDecoder().decode(Installation.self, from: Data(#"{"product":"roleband","instance":"0123456789abcdef01234567","api_origin":"http://127.0.0.1:8010","version":"0.2.0","format":1}"#.utf8))
}

/// No test reaches an engine on this Mac: the status read always finds none.
private let noEngine: @Sendable (Installation) async throws -> VerifiedStatus = { _ in throw ConnectionProblem.unavailable }

@MainActor
private func portModel(_ boundary: PortBoundary, preferences: UserDefaults,
                       free: @escaping @Sendable (Int) -> Bool = { _ in true }) -> LauncherModel {
    preferences.set(true, forKey: "setupCompleted")
    return LauncherModel(installation: .fixed(try! ownedInstallation()), mode: .owned(leftover: nil),
                         ownedEngine: boundary.service, readStatus: noEngine, preferences: preferences, language: "en",
                         portFree: free)
}

@MainActor
@Test func aHeldPortNamesItsProgramAndOffersAFreeOne() async throws {
    let boundary = PortBoundary(try ownedInstallation())
    let model = portModel(boundary, preferences: .scratch("port-test"))
    await boundary.hold(by: "Docker", suggestion: 8011)
    await model.refreshHost()
    #expect(model.hostState == .needsAttention)
    #expect(model.helpKey == "host-port-holder-body")
    // The title names the problem; the body names who holds the port and what happens next.
    #expect(model.text(model.titleKey, model.helpValues) == "Port 8010 is in use")
    #expect(model.text(try #require(model.helpKey), model.helpValues) == "Docker is using it. Scanning starts once Docker stops.")
    #expect(model.showsPortNote, "set up: Radar has been opened, so a move changes what the browser keeps")
    #expect(model.portSuggestion == 8011)

    // Another account's program cannot be looked into: the message says only that one holds the port.
    await boundary.hold(by: nil, suggestion: nil)
    await model.refreshHost()
    #expect(model.helpKey == "host-port-body")
    #expect(model.text(try #require(model.helpKey), model.helpValues) == "Another program is using it. Scanning starts once that program stops.")
    #expect(model.portSuggestion == nil, "no free port nearby, so no button promising one")
}

@MainActor
@Test func aPortOutsideTheRangeOrInUseIsRefusedAndNothingMoves() async throws {
    let boundary = PortBoundary(try ownedInstallation())
    let preferences = UserDefaults.scratch("port-test")
    let model = portModel(boundary, preferences: preferences, free: { $0 != 9000 })
    for port in [0, 80, 1023, 65536] {
        model.usePort(port)
        #expect(model.portRefusal == .invalid, "port \(port)")
    }
    model.usePort(6000)
    #expect(model.portRefusal == .blocked(6000))
    #expect(model.text(model.portRefusal!.key, model.portRefusal!.values) == "Browsers don't open port 6000. Choose another.")
    model.usePort(9000)
    #expect(model.portRefusal == .busy(9000))
    #expect(model.text(model.portRefusal!.key, model.portRefusal!.values) == "Port 9000 is in use. Choose another.")
    // The port the engine already has, with nothing holding it, needs nothing.
    model.usePort(8010)
    #expect(model.portRefusal == nil)
    await model.usePortAndWait(8010)
    #expect(await boundary.calls.isEmpty)
    #expect(preferences.object(forKey: EnginePort.preferenceKey) == nil)
    #expect(model.enginePort == 8010)
}

@MainActor
@Test func usingAnotherPortStopsMovesSavesAndStartsTheEngineThere() async throws {
    let boundary = PortBoundary(try ownedInstallation())
    let preferences = UserDefaults.scratch("port-test")
    let model = portModel(boundary, preferences: preferences)
    await boundary.hold(by: "Docker", suggestion: 8011)
    await model.refreshHost()
    await model.usePortAndWait(try #require(model.portSuggestion))
    #expect(await boundary.calls == ["stop", "use 8011", "start"])
    #expect(EnginePort.saved(in: preferences) == 8011)
    #expect(model.enginePort == 8011)
    #expect(model.hostState == .running && model.hostProblem == nil)
    #expect(await boundary.installation.apiOrigin == "http://127.0.0.1:8011")

    // Back to the default is stored as no choice at all.
    await model.usePortAndWait(Installation.ownedPort)
    #expect(await boundary.calls.suffix(3) == ["stop", "use 8010", "start"])
    #expect(preferences.object(forKey: EnginePort.preferenceKey) == nil)
    #expect(model.enginePort == 8010)
}

@MainActor
@Test func aMoveTheEngineRefusesLeavesTheSavedPortAsItWas() async throws {
    let installation = try ownedInstallation()
    let preferences = UserDefaults.scratch("port-test")
    preferences.set(true, forKey: "setupCompleted")
    let refusing = OwnedEngineService(start: {}, restart: {}, stop: {}, snapshot: { OwnedEngineSnapshot(state: .stopped) },
                                      use: { _ in throw HostProblem.invalidConfiguration })
    let model = LauncherModel(installation: .fixed(installation), mode: .owned(leftover: nil), ownedEngine: refusing,
                              readStatus: noEngine, preferences: preferences, language: "en", portFree: { _ in true })
    await model.usePortAndWait(8020)
    #expect(preferences.object(forKey: EnginePort.preferenceKey) == nil)
    #expect(model.enginePort == 8010)
    #expect(model.controlMessage == "engine-unconfirmed")
    // The reason stays beside the port the person chose, in Settings as on the status tab.
    #expect(model.portRefusal == .failed(8020))
    #expect(model.text(model.portRefusal!.key, model.portRefusal!.values) == "Couldn't move to port 8020. Try again.")
}

@Test func theSavedPortIsTheDefaultUntilAnAllowedOneIsChosen() {
    let preferences = UserDefaults.scratch("engine-port")
    #expect(EnginePort.saved(in: preferences) == 8010)
    for refused in [80, 1023, 6000, 65536, -1] {
        preferences.set(refused, forKey: EnginePort.preferenceKey)
        #expect(EnginePort.saved(in: preferences) == 8010, "\(refused) is no port the engine can use")
    }
    EnginePort.save(8123, in: preferences)
    #expect(EnginePort.saved(in: preferences) == 8123)
    EnginePort.save(8010, in: preferences)
    #expect(preferences.object(forKey: EnginePort.preferenceKey) == nil)
}

/// Whether `condition` came true within a few seconds.
@MainActor
private func eventually(_ condition: @MainActor () async -> Bool) async -> Bool {
    for _ in 0..<500 {
        if await condition() { return true }
        try? await Task.sleep(for: .milliseconds(10))
    }
    return await condition()
}

@MainActor
@Test func anOfferedPortTakenSinceIsRefusedAndTheNextFreeOneOffered() async throws {
    let taken = Taken()
    let boundary = PortBoundary(try ownedInstallation())
    let model = portModel(boundary, preferences: .scratch("port-test"), free: { !taken.contains($0) })
    await boundary.hold(by: "Docker", suggestion: 8011)
    await model.refreshHost()
    #expect(model.portSuggestion == 8011)

    // Another program takes 8011 before the click.
    taken.insert(8011)
    model.usePort(8011)
    #expect(model.portRefusal == .busy(8011))
    #expect(model.portSuggestion == 8012, "the button offers the next free port at once")
    #expect(await boundary.calls.isEmpty)
    // The engine's own record still says 8011; each refresh checks it again.
    await model.refreshHost()
    #expect(model.portSuggestion == 8012)
}

@MainActor
@Test func aQuitDuringAPortChangeLeavesTheEngineStopped() async throws {
    let gated = GatedEngine(try ownedInstallation())
    let preferences = UserDefaults.scratch("port-test")
    preferences.set(true, forKey: "setupCompleted")
    let model = LauncherModel(installation: .fixed(try ownedInstallation()), mode: .owned(leftover: nil),
                              ownedEngine: gated.service, readStatus: noEngine, preferences: preferences,
                              language: "en", portFree: { _ in true })
    model.usePort(8011)
    #expect(await eventually { await gated.stopping })
    // The quit cancels the change while the engine is still stopping.
    model.stop()
    await gated.release()
    #expect(await eventually { !model.controlBusy })
    try await Task.sleep(for: .milliseconds(50))
    #expect(await gated.calls == ["stop"], "nothing moves or starts after the quit")
    #expect(preferences.object(forKey: EnginePort.preferenceKey) == nil)
    #expect(model.enginePort == 8010)
}

/// Ports other programs hold, changed while a test runs.
private final class Taken: @unchecked Sendable {
    private let lock = NSLock()
    private var ports: Set<Int> = []
    func insert(_ port: Int) { lock.withLock { _ = ports.insert(port) } }
    func contains(_ port: Int) -> Bool { lock.withLock { ports.contains(port) } }
}

/// An owned engine whose first stop waits until the test lets it finish.
private actor GatedEngine {
    var calls: [String] = []
    private var gate: CheckedContinuation<Void, Never>?
    private var installation: Installation
    init(_ installation: Installation) { self.installation = installation }
    var stopping: Bool { gate != nil }
    func stop() async {
        calls.append("stop")
        if calls.count == 1 { await withCheckedContinuation { gate = $0 } }
    }
    func release() { gate?.resume(); gate = nil }
    func start() { calls.append("start") }
    func use(_ port: Int) throws -> Installation {
        calls.append("use \(port)")
        installation = try installation.on(port: port)
        return installation
    }
    nonisolated var service: OwnedEngineService {
        OwnedEngineService(start: { await self.start() }, restart: { await self.start() },
                           stop: { await self.stop() }, snapshot: { OwnedEngineSnapshot(state: .stopped) },
                           use: { try await self.use($0) })
    }
}

@MainActor
@Test func aPortTakenWhileTheEngineStopsSendsItBackAndKeepsTheSavedChoice() async throws {
    let boundary = PortBoundary(try ownedInstallation())
    let preferences = UserDefaults.scratch("port-test")
    let model = portModel(boundary, preferences: preferences)
    await boundary.takeOnStart(8030)
    await model.usePortAndWait(8030)
    #expect(await boundary.calls == ["stop", "use 8030", "start", "use 8010", "start"])
    #expect(preferences.object(forKey: EnginePort.preferenceKey) == nil, "the port that works stays the saved one")
    #expect(model.enginePort == 8010)
    #expect(model.portRefusal == .busy(8030))
    #expect(model.hostState == .running && model.hostProblem == nil)
}

@MainActor
@Test func setupReleasingItsHoldDuringAMoveStartsTheEngineOnTheNewPort() async throws {
    let home = FileManager.default.temporaryDirectory.appendingPathComponent("port-hold-\(UUID().uuidString)")
    let bundle = home.appendingPathComponent("Applications/RoleBand.app")
    try FileManager.default.createDirectory(at: bundle, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: home) }
    let gated = GatedEngine(try ownedInstallation())
    let preferences = UserDefaults.scratch("port-test")
    let model = LauncherModel(installation: .fixed(try ownedInstallation()), mode: .owned(leftover: nil),
                              ownedEngine: gated.service, readStatus: noEngine, preferences: preferences,
                              bundleURL: bundle, homeURL: home, language: "en", portFree: { _ in true })
    #expect(model.step == .welcome && model.engineHeld)
    model.usePort(8011)
    #expect(await eventually { await gated.stopping })
    // Setup continues past Welcome while the engine is still stopping.
    model.step = .connection
    #expect(!model.engineHeld)
    await gated.release()
    #expect(await eventually { !model.controlBusy })
    #expect(await gated.calls == ["stop", "use 8011", "start"])
    #expect(model.controlMessage == "engine-requested")
}

@MainActor
@Test func aStartRefusedForAnotherReasonKeepsTheNewPortSaved() async throws {
    let boundary = PortBoundary(try ownedInstallation())
    let preferences = UserDefaults.scratch("port-test")
    let model = portModel(boundary, preferences: preferences)
    await boundary.refuseStart(.databaseInUse)
    await model.usePortAndWait(8030)
    #expect(await boundary.calls == ["stop", "use 8030", "start"])
    // The engine stays on 8030 and starts there once the database is free, so 8030 is the saved port.
    #expect(EnginePort.saved(in: preferences) == 8030)
    #expect(model.enginePort == 8030)
    #expect(model.portRefusal == nil)
    #expect(model.hostProblem == .databaseInUse)
}

@MainActor
@Test func setupStoppedByAHeldPortSaysWhoHoldsItAndOffersTheMove() async throws {
    let home = FileManager.default.temporaryDirectory.appendingPathComponent("port-setup-\(UUID().uuidString)")
    let bundle = home.appendingPathComponent("Applications/RoleBand.app")
    try FileManager.default.createDirectory(at: bundle, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: home) }
    let boundary = PortBoundary(try ownedInstallation())
    let preferences = UserDefaults.scratch("port-test")
    let model = LauncherModel(installation: .fixed(try ownedInstallation()), mode: .owned(leftover: nil),
                              ownedEngine: boundary.service, readStatus: noEngine, preferences: preferences,
                              bundleURL: bundle, homeURL: home, language: "en", portFree: { _ in true })
    // Setup is past Welcome, on Get ready, where the engine prepares.
    model.step = .connection
    #expect(!model.setupCompleted && !model.engineHeld)
    #expect(model.setupStopKey == nil && model.setupDatabaseState == "creating")
    await boundary.hold(by: "Python", suggestion: 8011)
    await model.refreshHost()
    #expect(model.preparationFailed)
    // Setup says what holds the port instead of a service failure, and offers the free port.
    let key = try #require(model.setupStopKey)
    #expect(model.text(key, model.helpValues) == "Python is using it. Scanning starts once Python stops.")
    #expect(model.text(model.titleKey, model.helpValues) == "Port 8010 is in use")
    #expect(!model.showsPortNote, "during setup Radar has never been opened, so there is nothing to warn about")
    #expect(model.portSuggestion == 8011)
    #expect(model.setupDatabaseState == "waiting", "no database is being created while nothing runs")
    #expect(model.setupPortRefusal == nil)
    await model.usePortAndWait(8011)
    #expect(await boundary.calls == ["stop", "use 8011", "start"])
    #expect(model.setupStopKey == nil)
}

@MainActor
@Test func setupSaysWhyAMoveToAPortTakenMeanwhileWasRefused() async throws {
    let home = FileManager.default.temporaryDirectory.appendingPathComponent("port-setup-\(UUID().uuidString)")
    let bundle = home.appendingPathComponent("Applications/RoleBand.app")
    try FileManager.default.createDirectory(at: bundle, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: home) }
    let boundary = PortBoundary(try ownedInstallation())
    let model = LauncherModel(installation: .fixed(try ownedInstallation()), mode: .owned(leftover: nil),
                              ownedEngine: boundary.service, readStatus: noEngine, preferences: .scratch("port-test"),
                              bundleURL: bundle, homeURL: home, language: "en", portFree: { _ in true })
    model.step = .connection
    await boundary.hold(by: "Python", suggestion: 8011)
    await model.refreshHost()
    // Python still holds 8010, and another program takes 8011 before the engine starts there.
    await boundary.takeOnStart(8010)
    await boundary.takeOnStart(8011)
    await model.usePortAndWait(8011)
    #expect(await boundary.calls == ["stop", "use 8011", "start", "use 8010", "start"])
    #expect(model.setupStopKey != nil, "setup stays stopped on the held port")
    let refusal = try #require(model.setupPortRefusal)
    #expect(model.text(refusal.key, refusal.values) == "Port 8011 is in use. Choose another.")
}

@MainActor
@Test func aStartRefusedForAHeldPortAddsNoSecondMessage() async throws {
    let boundary = PortBoundary(try ownedInstallation())
    let model = portModel(boundary, preferences: .scratch("port-test"))
    await boundary.takeOnStart(8010)
    await model.startEngineAndWait()
    #expect(model.hostProblem == .portInUse)
    #expect(model.controlMessage == nil, "the status says why; no request line under it")
}

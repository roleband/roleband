import AppKit
import Foundation
import SwiftUI
import Testing
@testable import LauncherCore
@testable import RoleBandLauncher

private final class Clock: @unchecked Sendable {
    var now = Date(timeIntervalSince1970: 1_800_000_000)
    func advance(_ seconds: TimeInterval) { now = now.addingTimeInterval(seconds) }
}

private func releaseData(_ version: String) -> Data {
    try! JSONSerialization.data(withJSONObject: ["tag_name": "v" + version,
        "html_url": "https://github.com/roleband/roleband/releases/tag/v" + version,
        "body": "", "draft": false, "prerelease": false, "published_at": "2026-11-14T10:00:00Z",
        "assets": ReleaseFiles.all(version).map { ["name": $0, "state": "uploaded"] }])
}

@MainActor @Test func laterHoldsTheWindowForThreeDaysAndAfterTheThirdOnlyTheBadgeRemains() {
    let clock = Clock()
    let defaults = UserDefaults.scratch("update-window")
    let updates = LauncherUpdates(preferences: defaults, fetch: { releaseData("0.2.0") }, now: { clock.now }, authenticate: { _ in nil })
    defer { updates.stop() }
    #expect(updates.windowAllows("0.2.0"))
    for _ in 1...2 {
        updates.later("0.2.0")
        clock.advance(3 * 86400 - 1)
        #expect(!updates.windowAllows("0.2.0"))
        clock.advance(1)
        #expect(updates.windowAllows("0.2.0"))
    }
    updates.later("0.2.0")
    clock.advance(30 * 86400)
    #expect(!updates.windowAllows("0.2.0"))

    // A newer version starts its own count, and the record outlives a restart.
    #expect(updates.windowAllows("0.2.1"))
    updates.later("0.2.1")
    let restored = LauncherUpdates(preferences: defaults, fetch: { releaseData("0.2.1") }, now: { clock.now }, authenticate: { _ in nil })
    defer { restored.stop() }
    #expect(!restored.windowAllows("0.2.1"))
    clock.advance(3 * 86400)
    #expect(restored.windowAllows("0.2.1"))
}

@MainActor @Test func theUpdateWindowFloatsWithoutTakingFocusAndAnswersTheFirstClick() throws {
    _ = NSApplication.shared
    let release = try OfferedRelease.decode(releaseData("0.2.1"), from: .production)
    let other = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 200, height: 120), styleMask: [.titled], backing: .buffered, defer: false)
    other.isReleasedWhenClosed = false
    other.makeKeyAndOrderFront(nil)
    let keyBefore = NSApp.keyWindow
    let panel = UpdatePanel(title: "Version 0.2.1 is ready", content: UpdateWindowView(release: release, copy: LauncherCopy()))
    defer { panel.close(); other.close() }
    panel.present()
    #expect(panel.isVisible && !panel.isKeyWindow && NSApp.keyWindow === keyBefore)
    // Even asked outright, it never takes the keyboard.
    panel.makeKey()
    #expect(!panel.isKeyWindow && !panel.canBecomeKey && !panel.canBecomeMain)
    #expect(panel.styleMask.contains(.nonactivatingPanel) && panel.level == .floating && !panel.hidesOnDeactivate)
    #expect(!panel.collectionBehavior.contains(.fullScreenAuxiliary))
    #expect(panel.contentView?.acceptsFirstMouse(for: nil) == true)
    #expect(panel.frame.width >= 400 && panel.frame.height > 100, "\(panel.frame) \(panel.contentView?.fittingSize ?? .zero)")
}

@Test func eachUpdateStateOffersOnlyTheChoicesThatStillMatter() {
    #expect(UpdateWindowView.buttons(for: nil) == [.later, .update])
    #expect(UpdateWindowView.buttons(for: .downloading(received: 1, total: 2)) == [.cancel])
    #expect(UpdateWindowView.buttons(for: .paused(received: 1, total: 2)) == [.cancel])
    #expect(UpdateWindowView.buttons(for: .verifying).isEmpty && UpdateWindowView.buttons(for: .restarting).isEmpty)
    #expect(UpdateWindowView.buttons(for: .failed(.download)) == [.later, .retry])
    // A release signed differently installs only from its page, so Retry could only fail again.
    #expect(UpdateWindowView.buttons(for: .failed(.signer)) == [.later, .page])
}

@MainActor @Test func anUpdateInProgressKeepsItsVersionWhenANewerOfferArrives() async throws {
    let defaults = UserDefaults.scratch("update-window-version")
    let feed = Feed(version: "0.2.0")
    let updates = LauncherUpdates(preferences: defaults, fetch: { feed.data() }, authenticate: { _ in nil })
    defer { updates.stop() }
    await updates.checkManuallyAndWait()
    let installer = UpdateInstaller(operations: UpdateInstallerOperations(reserve: { 0 }, download: { _, _, _ in throw CancellationError() },
        prepare: { _ in throw CancellationError() }, discard: { _ in }, handOff: { _ in }))
    var acted: [String] = []
    let view = LiveUpdateWindow(updates: updates, installer: installer, copy: LauncherCopy(), actions: { _, version in
        acted.append(version)
        return UpdateWindowActions()
    })
    _ = view.body
    installer.show(.downloading(received: 1, total: 2), version: "0.2.0")
    feed.version = "0.3.0"
    await updates.checkManuallyAndWait()
    #expect(updates.offered?.version == "0.3.0")
    _ = view.body
    #expect(acted == ["0.2.0", "0.2.0"])
    // Once the update is answered, the window offers the newer version.
    installer.cancel()
    _ = view.body
    #expect(acted.last == "0.3.0")
}

private final class Feed: @unchecked Sendable {
    var version: String
    init(version: String) { self.version = version }
    func data() -> Data { releaseData(version) }
}

@MainActor @Test func theWindowGrowsWhenTheOfferTurnsIntoProgress() async throws {
    let defaults = UserDefaults.scratch("update-window-size")
    let updates = LauncherUpdates(preferences: defaults, fetch: { releaseData("0.2.1") }, authenticate: { _ in nil })
    defer { updates.stop() }
    await updates.checkManuallyAndWait()
    let installer = UpdateInstaller(operations: UpdateInstallerOperations(reserve: { 0 }, download: { _, _, _ in throw CancellationError() },
        prepare: { _ in throw CancellationError() }, discard: { _ in }, handOff: { _ in }))
    let panel = UpdatePanel(title: "Version 0.2.1 is ready", content: LiveUpdateWindow(updates: updates, installer: installer,
        copy: LauncherCopy(), actions: { _, _ in UpdateWindowActions() }))
    defer { panel.close() }
    panel.present()
    let offer = panel.frame.height
    #expect(offer > 100)
    installer.show(.downloading(received: 1, total: 2), version: "0.2.1")
    for _ in 0..<20 where panel.frame.height <= offer {
        try await Task.sleep(for: .milliseconds(25))
        panel.contentView?.layoutSubtreeIfNeeded()
    }
    #expect(panel.frame.height > offer)
}

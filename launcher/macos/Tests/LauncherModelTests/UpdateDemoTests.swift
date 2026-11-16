import Foundation
import Testing
import LauncherCore
@testable import RoleBandLauncher

@Test func demoFeedRequiresBothPreviewIdentityAndAnAbsoluteRegistrationAndFeedPath() {
    var info: [String: Any] = ["RoleBandDemoReleaseFile": "/tmp/release.json"]
    #expect(UpdateDemo.file(in: info) == nil)
    info["RoleBandPreview"] = true
    #expect(UpdateDemo.file(in: info) == nil)
    info["RoleBandRegistration"] = "/tmp/installation.json"
    #expect(UpdateDemo.file(in: info)?.path == "/tmp/release.json")
    info["RoleBandDemoReleaseFile"] = "relative.json"
    #expect(UpdateDemo.file(in: info) == nil)
}

@MainActor @Test func demoChecksReadTheMutableFileThroughNormalValidationAndFailClosedForInvalidConfiguration() async throws {
    do {
        let preferences = UserDefaults.scratch("update-demo-tests")
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent("release.json")
        let info: [String: Any] = ["RoleBandPreview": true, "RoleBandRegistration": "/tmp/installation.json",
                                   "RoleBandDemoReleaseFile": file.path]
        let updates = UpdateDemo.updates(preferences: preferences, copy: LauncherCopy(), info: info)
        defer { updates.stop() }
        let release: [String: Any] = ["tag_name": "v0.2.0", "html_url": "https://github.com/roleband/roleband/releases/tag/v0.2.0",
                                    "body": "Dummy release.", "draft": false, "prerelease": false,
                                    "assets": ReleaseFiles.all("0.2.0").map { ["name": $0, "state": "uploaded"] }]
        try JSONSerialization.data(withJSONObject: release).write(to: file, options: .atomic)
        await updates.checkManuallyAndWait()
        #expect(updates.offered?.version == "0.2.0" && updates.consent == .undecided)
        try Data("{}".utf8).write(to: file, options: .atomic)
        await updates.checkManuallyAndWait()
        #expect(updates.messageKey == "update-failed" && updates.offered?.version == "0.2.0")
        // A valid feed again, so only the missing preview identity can fail the next check.
        try JSONSerialization.data(withJSONObject: release).write(to: file, options: .atomic)
        let invalid = UpdateDemo.updates(preferences: preferences, copy: LauncherCopy(),
                                        info: ["RoleBandDemoReleaseFile": file.path])
        defer { invalid.stop() }
        await invalid.checkManuallyAndWait()
        #expect(invalid.messageKey == "update-failed")
    }
}

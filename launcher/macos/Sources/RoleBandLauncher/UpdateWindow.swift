import AppKit
import LauncherCore
import SwiftUI

/// What the update window can ask the app to do.
struct UpdateWindowActions {
    var later: () -> Void = {}
    var update: () -> Void = {}
    var cancel: () -> Void = {}
    var notes: () -> Void = {}
    var page: () -> Void = {}
}

/// The window that appears by itself when a daily check finds a version. It carries the update from
/// the offer to the restart, since the person it is for may never open the panel.
struct UpdateWindowView: View {
    let release: OfferedRelease
    let copy: LauncherCopy
    var activity: UpdateActivity?
    /// The version an update in progress installs; a newer offer found meanwhile does not rename it.
    var installing: String?
    var actions = UpdateWindowActions()
    private var version: String { activity == nil ? release.version : installing ?? release.version }

    var body: some View {
        PaletteReader { p in
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top, spacing: 14) {
                    Image(nsImage: NSApp.applicationIconImage ?? NSImage()).resizable().frame(width: 52, height: 52)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(copy.text("update-ready", ["version": version]))
                            .font(.system(size: 15, weight: .semibold)).foregroundStyle(p.ink).accessibilityAddTraits(.isHeader)
                        if version == release.version, let published = release.published {
                            Text(copy.text("update-released", ["date": published.formatted(.dateTime.day().month(.wide).locale(copy.locale))]))
                                .font(PanelType.fact).foregroundStyle(p.secondary)
                        }
                    }.padding(.top, 6)
                    Spacer(minLength: 0)
                }
                Text(copy.text("update-window-body")).font(.system(size: 13)).foregroundStyle(p.secondary)
                    .lineSpacing(3).fixedSize(horizontal: false, vertical: true)
                if activity == nil, let notice = release.beforeYouUpdate { noticeBox(notice, p) }
                if let activity { progress(activity, p) }
                footer(p)
            }
            .padding(20).frame(width: 400, alignment: .leading)
            .background(Color(nsColor: .windowBackgroundColor))
        }
    }

    private func noticeBox(_ notice: String, _ p: LaunchPalette) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.circle.fill").foregroundStyle(p.warning).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(copy.text("update-before-you-update")).font(PanelType.row).foregroundStyle(p.ink)
                Text(verbatim: notice.split(separator: "\n").map { $0.trimmingCharacters(in: .whitespaces) }.joined(separator: " "))
                    .font(PanelType.fact).foregroundStyle(p.secondary).lineSpacing(2).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10).frame(maxWidth: .infinity, alignment: .leading)
        .background(p.warning.opacity(0.1), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(p.warning.opacity(0.3), lineWidth: 0.7))
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private func progress(_ activity: UpdateActivity, _ p: LaunchPalette) -> some View {
        switch activity {
        case .downloading(let received, let total):
            progressLine(UpdateStep.title(activity, version: version, copy: copy),
                         detail: UpdateSize.progress(received: received, total: total, copy: copy),
                         fraction: total > 0 ? Double(received) / Double(total) : 0, color: p.cyan, p)
        case .paused(let received, let total):
            progressLine(copy.text("update-paused"), detail: copy.text("update-paused-caption"),
                         fraction: total > 0 ? Double(received) / Double(total) : 0, color: p.graphic, p)
        case .verifying, .restarting:
            progressLine(UpdateStep.title(activity, version: version, copy: copy), detail: nil, working: true,
                         fraction: 1, color: p.cyan, p)
        case .failed(let failure):
            let (title, caption) = UpdateFailureText.of(failure, version: version, copy: copy)
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "exclamationmark.circle.fill").foregroundStyle(p.warning).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(PanelType.row).foregroundStyle(p.ink)
                    Text(caption).font(PanelType.fact).foregroundStyle(p.secondary).fixedSize(horizontal: false, vertical: true)
                }
            }.accessibilityElement(children: .combine)
        }
    }

    private func progressLine(_ title: String, detail: String?, working: Bool = false, fraction: Double, color: Color,
                              _ p: LaunchPalette) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(title).font(PanelType.row).foregroundStyle(p.ink)
                Spacer()
                if let detail { Text(detail).font(PanelType.fact).foregroundStyle(p.secondary).monospacedDigit() }
                if working { ProgressView().controlSize(.small).accessibilityHidden(true) }
            }
            ProgressLine(fraction: fraction, color: color, track: p.track).accessibilityHidden(true)
        }.accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private func footer(_ p: LaunchPalette) -> some View {
        HStack(spacing: 8) {
            Button(copy.text("notes-title"), action: actions.notes).buttonStyle(LinkButtonStyle(font: PanelType.control))
            Spacer()
            ForEach(Self.buttons(for: activity), id: \.self) { button in
                switch button {
                case .later: Button(copy.text("update-later"), action: actions.later).buttonStyle(LaunchButtonStyle(palette: p))
                case .update: Button(copy.text("update-install"), action: actions.update).buttonStyle(LaunchButtonStyle(palette: p, primary: true))
                case .retry: Button(copy.text("retry"), action: actions.update).buttonStyle(LaunchButtonStyle(palette: p, primary: true))
                case .cancel: Button(copy.text("update-cancel"), action: actions.cancel).buttonStyle(LaunchButtonStyle(palette: p))
                case .page: Button(copy.text("update-release-page"), action: actions.page).buttonStyle(LaunchButtonStyle(palette: p, primary: true))
                }
            }
        }.frame(minHeight: 28)
    }

    enum Choice { case later, update, retry, cancel, page }
    /// The buttons beside What's new. The notice, when there is one, is already on the window, so
    /// Update needs no Read first step. Once the update is checked and restarting, nothing is left to
    /// choose. A release signed differently can only be installed from its page, so it offers that.
    static func buttons(for activity: UpdateActivity?) -> [Choice] {
        switch activity {
        case nil: [.later, .update]
        case .downloading?, .paused?: [.cancel]
        case .verifying?, .restarting?: []
        case .failed(.signer)?: [.later, .page]
        case .failed?: [.later, .retry]
        }
    }
}

/// A failed update's two lines, for the update window.
enum UpdateFailureText {
    static func of(_ failure: UpdateFailure, version: String, copy: LauncherCopy) -> (title: String, caption: String) {
        switch failure {
        case .download: (copy.text("update-download-failed", ["version": version]), copy.text("update-download-failed-caption"))
        case .check: (copy.text("update-check-failed", ["version": version]), copy.text("update-nothing-installed"))
        case .space(let required): (copy.text("update-no-space"),
                                    copy.text("update-no-space-caption", ["size": UpdateSize.bytes(required, locale: copy.locale)]))
        case .restart: (copy.text("update-restart-failed"), copy.text("update-nothing-installed"))
        case .signer: (copy.text("update-signer-changed", ["version": version]), copy.text("update-signer-changed-caption"))
        }
    }
}

/// The window bound to the live offer and installer.
struct LiveUpdateWindow: View {
    @ObservedObject var updates: LauncherUpdates
    @ObservedObject var installer: UpdateInstaller
    let copy: LauncherCopy
    /// Actions for a version: the one an update in progress installs, else the offer.
    let actions: (OfferedRelease, String) -> UpdateWindowActions

    var body: some View {
        if let release = updates.offered {
            let version = installer.activity == nil ? release.version : installer.version ?? release.version
            UpdateWindowView(release: release, copy: copy, activity: installer.activity, installing: installer.version,
                             actions: actions(release, version))
        }
    }
}

/// A floating panel that never takes focus: whatever the person is typing keeps going, and its
/// buttons answer the first click. It cannot become key, so it has no Escape; Later is its way out.
final class UpdatePanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }

    convenience init<Content: View>(title: String, content: Content) {
        self.init(contentRect: NSRect(x: 0, y: 0, width: 400, height: 200),
                  styleMask: [.titled, .fullSizeContentView, .nonactivatingPanel], backing: .buffered, defer: false)
        self.title = title
        titleVisibility = .hidden
        titlebarAppearsTransparent = true
        for button in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton] { standardWindowButton(button)?.isHidden = true }
        isFloatingPanel = true
        level = .floating
        hidesOnDeactivate = false
        isReleasedWhenClosed = false
        isMovableByWindowBackground = true
        // No full-screen auxiliary behaviour: over a full-screen app it waits on the desktop
        // instead of pulling the person out.
        collectionBehavior = [.moveToActiveSpace]
        let host = FirstClickHostingView(rootView: content)
        host.layoutSubtreeIfNeeded()
        let size = host.fittingSize
        contentView = host
        setContentSize(size)
        // The window follows its content as the offer turns into progress or a failure. Set after the
        // first size, since the hosting view reports none until it has laid out.
        host.sizingOptions = [.minSize, .maxSize]
    }

    func present() {
        center()
        orderFrontRegardless()
    }
}

final class FirstClickHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

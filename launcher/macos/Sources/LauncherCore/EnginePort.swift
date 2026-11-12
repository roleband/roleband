import Darwin
import Foundation

/// Another program listens on the port the app's engine serves on.
public struct PortConflict: Equatable, Sendable {
    public let port: Int
    /// The program holding the port, when it runs under this account; another account's programs
    /// cannot be looked into.
    public let holder: String?
    /// A free port nearby, offered as the one-press way out.
    public let suggestion: Int?

    public init(port: Int, holder: String?, suggestion: Int?) {
        self.port = port
        self.holder = holder
        self.suggestion = suggestion
    }

    /// What is on `port` now, and an unused port after it.
    public static func find(_ port: Int, isFree: (Int) -> Bool = EnginePort.isUnused) -> PortConflict {
        PortConflict(port: port, holder: EnginePort.holder(of: port), suggestion: EnginePort.suggestion(after: port, isFree: isFree))
    }
}

/// The loopback port of the app's own engine: the person's choice, or `Installation.ownedPort`.
/// The browser keeps bookmarks and a page's saved settings per address, so the port changes only
/// when the person changes it.
public enum EnginePort {
    public static let preferenceKey = "enginePort"
    /// Ports below 1024 need administrator rights to listen on.
    public static let allowed = 1024...65535
    /// Ports above 1023 that browsers refuse to load: the Fetch standard's bad ports, which
    /// Safari, Chrome and Firefox all block. Radar could not open on one of them.
    public static let browserRefused: Set<Int> = [1719, 1720, 1723, 2049, 3659, 4045, 4190, 5060, 5061, 6000,
                                                 6566, 6665, 6666, 6667, 6668, 6669, 6679, 6697, 10080]
    /// How far past a busy port a free one is looked for.
    static let searchSpan = 100

    /// A port the engine can listen on without administrator rights and a browser can open.
    public static func usable(_ port: Int) -> Bool { allowed.contains(port) && !browserRefused.contains(port) }

    public static func saved(in preferences: UserDefaults) -> Int {
        let value = preferences.integer(forKey: preferenceKey)
        return usable(value) ? value : Installation.ownedPort
    }

    /// The default port is stored as no choice, so a later default would apply to it.
    public static func save(_ port: Int, in preferences: UserDefaults) {
        precondition(usable(port), "no engine port: \(port)")
        if port == Installation.ownedPort { preferences.removeObject(forKey: preferenceKey) }
        else { preferences.set(port, forKey: preferenceKey) }
    }

    /// Whether the engine could listen on `port` now. Binds 127.0.0.1 with the reuse option the
    /// engine's server sets, so a port the last engine left in TIME_WAIT counts as free, as it
    /// does for the engine. A program listening on 127.0.0.1 makes it busy; this account's
    /// programs listening on every address do not, since the engine can still bind 127.0.0.1.
    public static func isFree(_ port: Int) -> Bool {
        guard (1...65535).contains(port) else { return false }
        return binds(AF_INET, "127.0.0.1", port)
    }

    /// Whether no program listens on `port` on either loopback address or on every address, in
    /// IPv4 or IPv6: the test for a port the person moves the engine to. An engine on 127.0.0.1
    /// takes that address's connections from a program listening on every address, so such a
    /// port is not offered. The probes use the reuse option too, so a port in TIME_WAIT, such as
    /// the one the engine just left, still counts as unused.
    public static func isUnused(_ port: Int) -> Bool {
        guard (1...65535).contains(port) else { return false }
        return binds(AF_INET, "127.0.0.1", port) && binds(AF_INET, "0.0.0.0", port)
            && binds(AF_INET6, "::1", port) && binds(AF_INET6, "::", port)
    }

    /// Whether a socket of `family` can bind `address` on `port` with SO_REUSEADDR, then lets go.
    /// An IPv6 probe is IPv6 only, so each family is probed on its own.
    private static func binds(_ family: Int32, _ address: String, _ port: Int) -> Bool {
        let fd = socket(family, SOCK_STREAM, IPPROTO_TCP)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        // A program the app starts meanwhile must not inherit the probe and keep the port.
        _ = fcntl(fd, F_SETFD, FD_CLOEXEC)
        var on: Int32 = 1
        guard setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &on, socklen_t(MemoryLayout<Int32>.size)) == 0 else { return false }
        if family == AF_INET6 {
            var storage = sockaddr_in6()
            guard setsockopt(fd, IPPROTO_IPV6, IPV6_V6ONLY, &on, socklen_t(MemoryLayout<Int32>.size)) == 0,
                  inet_pton(AF_INET6, address, &storage.sin6_addr) == 1 else { return false }
            storage.sin6_len = UInt8(MemoryLayout<sockaddr_in6>.size)
            storage.sin6_family = sa_family_t(AF_INET6)
            storage.sin6_port = in_port_t(UInt16(port).bigEndian)
            return withUnsafePointer(to: &storage) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in6>.size)) == 0 }
            }
        }
        var storage = sockaddr_in()
        guard inet_pton(AF_INET, address, &storage.sin_addr) == 1 else { return false }
        storage.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        storage.sin_family = sa_family_t(AF_INET)
        storage.sin_port = in_port_t(UInt16(port).bigEndian)
        return withUnsafePointer(to: &storage) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0 }
        }
    }

    /// The first unused usable port after `port`, among the next `searchSpan` ones.
    public static func suggestion(after port: Int, isFree: (Int) -> Bool = isUnused) -> Int? {
        let first = max(port + 1, allowed.lowerBound)
        let last = min(first + searchSpan - 1, allowed.upperBound)
        guard first <= last else { return nil }
        return (first...last).first(where: { usable($0) && isFree($0) })
    }

    /// The name of a program of this account listening on TCP `port`, or nil when none is: the
    /// kernel answers only for this account's own processes.
    public static func holder(of port: Int) -> String? {
        listener(on: port).flatMap(name)
    }

    static func listener(on port: Int) -> pid_t? {
        let count = proc_listpids(UInt32(PROC_UID_ONLY), UInt32(getuid()), nil, 0)
        guard count > 0 else { return nil }
        var pids = [pid_t](repeating: 0, count: Int(count) / MemoryLayout<pid_t>.size + 16)
        let filled = proc_listpids(UInt32(PROC_UID_ONLY), UInt32(getuid()), &pids, Int32(pids.count * MemoryLayout<pid_t>.size))
        guard filled > 0 else { return nil }
        return pids.prefix(Int(filled) / MemoryLayout<pid_t>.size).first { $0 > 0 && listens($0, on: port) }
    }

    private static func listens(_ pid: pid_t, on port: Int) -> Bool {
        let size = proc_pidinfo(pid, PROC_PIDLISTFDS, 0, nil, 0)
        guard size > 0 else { return false }
        var descriptors = [proc_fdinfo](repeating: proc_fdinfo(), count: Int(size) / MemoryLayout<proc_fdinfo>.size + 8)
        let filled = proc_pidinfo(pid, PROC_PIDLISTFDS, 0, &descriptors, Int32(descriptors.count * MemoryLayout<proc_fdinfo>.size))
        guard filled > 0 else { return false }
        for descriptor in descriptors.prefix(Int(filled) / MemoryLayout<proc_fdinfo>.size)
        where descriptor.proc_fdtype == UInt32(PROX_FDTYPE_SOCKET) {
            var info = socket_fdinfo()
            let length = Int32(MemoryLayout<socket_fdinfo>.size)
            guard proc_pidfdinfo(pid, descriptor.proc_fd, PROC_PIDFDSOCKETINFO, &info, length) == length,
                  info.psi.soi_kind == SOCKINFO_TCP else { continue }
            let tcp = info.psi.soi_proto.pri_tcp
            // The local port is kept in network byte order in the low 16 bits.
            let local = Int(UInt16(bigEndian: UInt16(truncatingIfNeeded: tcp.tcpsi_ini.insi_lport)))
            if local == port && tcp.tcpsi_state == TSI_S_LISTEN && takesLoopback(tcp.tcpsi_ini) { return true }
        }
        return false
    }

    /// Whether a listener at this local address keeps the engine from binding 127.0.0.1. The
    /// engine binds with SO_REUSEADDR, and the kernel lets it join a port that a socket of the same
    /// account holds on every address, so only a listener on 127.0.0.1 itself refuses it, in IPv4
    /// or as an IPv4-mapped IPv6 address. Every other listener shares the port number only.
    static func takesLoopback(_ ini: in_sockinfo) -> Bool {
        let loopback = in_addr_t(UInt32(INADDR_LOOPBACK).bigEndian)
        if ini.insi_vflag & UInt8(INI_IPV4) != 0, ini.insi_laddr.ina_46.i46a_addr4.s_addr == loopback { return true }
        if ini.insi_vflag & UInt8(INI_IPV6) != 0 {
            var address = ini.insi_laddr.ina_6
            let mapped: [UInt8] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xff, 0xff, 127, 0, 0, 1]
            if withUnsafeBytes(of: &address, { Array($0) }) == mapped { return true }
        }
        return false
    }

    /// An app by its bundle's name, any other program by its executable's; nil once the process
    /// has gone, so a program that quit after it was found is not named by an empty string.
    static func name(_ pid: pid_t) -> String? {
        guard let path = LaunchMode.executable(pid) else {
            var buffer = [CChar](repeating: 0, count: 2 * Int(MAXCOMLEN) + 1)
            guard proc_name(pid, &buffer, UInt32(buffer.count)) > 0 else { return nil }
            let name = String(decoding: buffer.prefix { $0 != 0 }.map(UInt8.init(bitPattern:)), as: UTF8.self)
            return name.isEmpty ? nil : name
        }
        if let app = path.pathComponents.firstIndex(where: { $0.hasSuffix(".app") }) {
            return String(path.pathComponents[app].dropLast(4))
        }
        return path.lastPathComponent
    }
}

public extension Installation {
    /// The same engine served on another loopback port.
    func on(port: Int) throws -> Installation {
        let moved = Installation(product: product, instance: instance, apiOrigin: "http://127.0.0.1:\(port)", version: version, format: format)
        _ = try moved.target()
        return moved
    }
}

public extension UserDefaults {
    /// Preferences for one render or test. A suite named by an absolute path is the plist at that path,
    /// so these sit in the temporary folder, which macOS clears, and never add a domain to
    /// ~/Library/Preferences.
    static func scratch(_ label: String) -> UserDefaults {
        UserDefaults(suiteName: FileManager.default.temporaryDirectory
            .appendingPathComponent("roleband-\(label)-\(UUID().uuidString)").path)!
    }
}

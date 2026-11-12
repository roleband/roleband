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

    /// What is on `port` now, and a free port after it.
    public static func find(_ port: Int, isFree: (Int) -> Bool = EnginePort.isFree) -> PortConflict {
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
    /// does for the engine, and a listening program anywhere on the port does not.
    public static func isFree(_ port: Int) -> Bool {
        guard (1...65535).contains(port) else { return false }
        let fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var reuse: Int32 = 1
        guard setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, socklen_t(MemoryLayout<Int32>.size)) == 0 else { return false }
        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = in_port_t(UInt16(port).bigEndian)
        address.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))
        return withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0 }
        }
    }

    /// The first free usable port after `port`, among the next `searchSpan` ones.
    public static func suggestion(after port: Int, isFree: (Int) -> Bool = isFree) -> Int? {
        let first = max(port + 1, allowed.lowerBound)
        let last = min(first + searchSpan - 1, allowed.upperBound)
        guard first <= last else { return nil }
        return (first...last).first(where: { usable($0) && isFree($0) })
    }

    /// The name of a program of this account listening on TCP `port`, or nil when none is: the
    /// kernel answers only for this account's own processes.
    public static func holder(of port: Int) -> String? {
        listener(on: port).map(name)
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

    /// Whether a listener at this local address keeps the engine from binding 127.0.0.1: one on
    /// 127.0.0.1 itself or on every address, in IPv4 or as a dual-stack IPv6 socket. A listener on
    /// another address, ::1 included, shares the port number without holding the engine's address.
    static func takesLoopback(_ ini: in_sockinfo) -> Bool {
        let loopback = in_addr_t(UInt32(INADDR_LOOPBACK).bigEndian)
        if ini.insi_vflag & UInt8(INI_IPV4) != 0 {
            let address = ini.insi_laddr.ina_46.i46a_addr4.s_addr
            if address == INADDR_ANY || address == loopback { return true }
        }
        if ini.insi_vflag & UInt8(INI_IPV6) != 0 {
            var address = ini.insi_laddr.ina_6
            let bytes = withUnsafeBytes(of: &address) { Array($0) }
            if bytes.allSatisfy({ $0 == 0 }) { return true }
            let mapped: [UInt8] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xff, 0xff, 127, 0, 0, 1]
            if bytes == mapped { return true }
        }
        return false
    }

    /// An app by its bundle's name, any other program by its executable's.
    static func name(_ pid: pid_t) -> String {
        guard let path = LaunchMode.executable(pid) else {
            var buffer = [CChar](repeating: 0, count: 2 * Int(MAXCOMLEN) + 1)
            proc_name(pid, &buffer, UInt32(buffer.count))
            return String(decoding: buffer.prefix { $0 != 0 }.map(UInt8.init(bitPattern:)), as: UTF8.self)
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

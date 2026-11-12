import Darwin
import Foundation
import Testing
@testable import LauncherCore

/// A TCP listener on a free loopback port, owned by this test process.
final class Listener {
    let fd: Int32
    let port: Int
    init(address: String = "127.0.0.1", port: Int = 0) throws {
        let fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
        self.fd = fd
        var bound = sockaddr_in()
        bound.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        bound.sin_family = sa_family_t(AF_INET)
        bound.sin_addr = in_addr(s_addr: inet_addr(address))
        bound.sin_port = in_port_t(UInt16(port).bigEndian)
        let ok = withUnsafePointer(to: &bound) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0 }
        }
        try #require(ok && listen(fd, 4) == 0, "could not listen: \(errno)")
        var length = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &bound) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &length) }
        }
        self.port = Int(UInt16(bigEndian: bound.sin_port))
    }
    func close() { Darwin.close(fd) }
}

@Test func aListeningPortIsNotFreeAndIsFreeAgainOnceItsProgramLetsGo() throws {
    let listener = try Listener()
    #expect(!EnginePort.isFree(listener.port))
    listener.close()
    #expect(EnginePort.isFree(listener.port))
    #expect(!EnginePort.isFree(0) && !EnginePort.isFree(70000))
}

@Test func theProgramHoldingAPortIsNamedWhenItIsThisAccounts() throws {
    let listener = try Listener()
    defer { listener.close() }
    #expect(EnginePort.listener(on: listener.port) == getpid())
    #expect(EnginePort.holder(of: listener.port) == EnginePort.name(getpid()))
    #expect(!(EnginePort.holder(of: listener.port) ?? "").isEmpty)
    let conflict = PortConflict.find(listener.port)
    #expect(conflict.port == listener.port && conflict.holder != nil)
    #expect(conflict.suggestion.map { $0 > listener.port && EnginePort.isFree($0) } == true)
}

@Test func nothingHoldsAPortNoProgramListensOn() throws {
    let listener = try Listener()
    listener.close()
    #expect(EnginePort.holder(of: listener.port) == nil)
}

@Test func anAppIsNamedByItsBundleAndAnyOtherProgramByItsExecutable() {
    // This process is the test runner: a plain executable, or a helper inside Xcode's app bundle.
    let name = EnginePort.name(getpid())
    let path = LaunchMode.executable(getpid())!
    if let app = path.pathComponents.first(where: { $0.hasSuffix(".app") }) { #expect(name == String(app.dropLast(4))) }
    else { #expect(name == path.lastPathComponent) }
}

@Test func theSuggestionIsTheFirstFreePortAfterTheTakenOne() {
    let taken: Set<Int> = [9001, 9002]
    #expect(EnginePort.suggestion(after: 9000, isFree: { !taken.contains($0) }) == 9003)
    #expect(EnginePort.suggestion(after: 9000, isFree: { _ in false }) == nil)
    #expect(EnginePort.suggestion(after: 65535, isFree: { _ in true }) == nil)
    #expect(EnginePort.suggestion(after: 80, isFree: { _ in true }) == 1024, "never a port that needs administrator rights")
    #expect(EnginePort.suggestion(after: 5999, isFree: { _ in true }) == 6001, "never a port browsers refuse to open")
    #expect(EnginePort.suggestion(after: 6664, isFree: { _ in true }) == 6670)
    #expect(EnginePort.usable(8010) && !EnginePort.usable(6000) && !EnginePort.usable(10080) && !EnginePort.usable(1023))
}

@Test func anInstallationOnAnotherPortKeepsItsIdentity() throws {
    let installation = try JSONDecoder().decode(Installation.self, from: Data(#"{"product":"roleband","instance":"0123456789abcdef01234567","api_origin":"http://127.0.0.1:8010","version":"0.2.0","format":1}"#.utf8))
    let moved = try installation.on(port: 8123)
    #expect(moved.apiOrigin == "http://127.0.0.1:8123")
    #expect(moved.instance == installation.instance && moved.version == installation.version && moved.product == installation.product)
    #expect(throws: ConnectionProblem.invalidInstallation) { try installation.on(port: 0) }
}

/// A TCP listener on ::1, the IPv6 loopback, which is not the engine's 127.0.0.1.
private final class IPv6Listener {
    let fd: Int32
    init(port: Int) throws {
        fd = socket(AF_INET6, SOCK_STREAM, IPPROTO_TCP)
        var only: Int32 = 1
        setsockopt(fd, IPPROTO_IPV6, IPV6_V6ONLY, &only, socklen_t(MemoryLayout<Int32>.size))
        var bound = sockaddr_in6()
        bound.sin6_len = UInt8(MemoryLayout<sockaddr_in6>.size)
        bound.sin6_family = sa_family_t(AF_INET6)
        bound.sin6_addr = in6addr_loopback
        bound.sin6_port = in_port_t(UInt16(port).bigEndian)
        let ok = withUnsafePointer(to: &bound) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in6>.size)) == 0 }
        }
        try #require(ok && listen(fd, 4) == 0, "could not listen on ::1: \(errno)")
    }
    func close() { Darwin.close(fd) }
}

@Test func aListenerOnAnotherAddressIsNotNamedAsTheHolder() throws {
    let probe = try Listener()
    probe.close()
    let other = try IPv6Listener(port: probe.port)
    defer { other.close() }
    // The port number is taken on ::1 only: 127.0.0.1 is free, and no program holds it.
    #expect(EnginePort.isFree(probe.port))
    #expect(EnginePort.listener(on: probe.port) == nil)
    let loopback = try Listener(port: probe.port)
    defer { loopback.close() }
    #expect(EnginePort.listener(on: probe.port) == getpid(), "the 127.0.0.1 listener is the holder")
}

@Test func onlyLoopbackAndEveryAddressHoldTheEnginesAddress() {
    func ipv4(_ address: String) -> in_sockinfo {
        var info = in_sockinfo()
        info.insi_vflag = UInt8(INI_IPV4)
        info.insi_laddr.ina_46.i46a_addr4.s_addr = inet_addr(address)
        return info
    }
    func ipv6(_ bytes: [UInt8]) -> in_sockinfo {
        var info = in_sockinfo()
        info.insi_vflag = UInt8(INI_IPV6)
        withUnsafeMutableBytes(of: &info.insi_laddr.ina_6) { $0.copyBytes(from: bytes) }
        return info
    }
    #expect(EnginePort.takesLoopback(ipv4("127.0.0.1")))
    #expect(EnginePort.takesLoopback(ipv4("0.0.0.0")))
    #expect(!EnginePort.takesLoopback(ipv4("192.168.1.20")))
    #expect(!EnginePort.takesLoopback(ipv4("127.0.0.2")))
    #expect(EnginePort.takesLoopback(ipv6([UInt8](repeating: 0, count: 16))), "a dual-stack socket on every address")
    #expect(EnginePort.takesLoopback(ipv6([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xff, 0xff, 127, 0, 0, 1])))
    #expect(!EnginePort.takesLoopback(ipv6([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1])), "::1 is not 127.0.0.1")
}

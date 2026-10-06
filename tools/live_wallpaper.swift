// Shows the Listening Point frame for the current minute on every screen, just above the desktop
// picture and below the desktop icons, switching on each minute with a short cross-fade.
//
// macOS's own time-of-day wallpapers can switch every minute, but the wallpaper agent caches every
// frame it shows as a ~20 MB bitmap and never prunes them, so 1,440 frames a day would fill the
// disk. This window does the per-minute part instead; the system wallpaper is an hourly HEIC of the
// same day, which shows on the lock screen, in Mission Control, while switching Spaces, and
// whenever this isn't running. Each hour this also deletes the agent's bitmaps of older versions of
// our wallpaper files (it needs Full Disk Access for that; the result is in ROOT/.cache-clean).
// Without access macOS shows a "data access blocked" notice, so after a refusal it waits a week
// before trying again (delete ROOT/.cache-clean and restart it after granting access).
//
// usage: live_wallpaper [ROOT]   frames are ROOT/days/YYYY-MM-DD/HHMM.jpg (local clock time);
//        when today's frame is missing it uses the same minute from the newest earlier day,
//        and with nothing at all it hides and lets the system wallpaper show. It also starts the
//        render job (a LaunchAgent) at once when today's frames are missing, e.g. after a long sleep.
import AppKit
import CryptoKit
import ImageIO
import QuartzCore

let wallpaperCache = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(
    "Library/Containers/com.apple.wallpaper.agent/Data/Library/Caches/com.apple.wallpaper.caches/extension-com.apple.wallpaper.extension.image")

final class Live {
    let root: URL
    var windows: [NSWindow] = []
    var shown = ""
    var timer: DispatchSourceTimer?
    var lastKick = Date.distantPast
    var lastClean = Date.distantPast

    init(root: URL) { self.root = root }

    /// The agent names each cached bitmap sha256(path)-W-H-frame-<mtime>.bmp, the mtime being the
    /// file's modification time since 2001 as a big-endian double. Delete ours that don't match
    /// the file now on disk; never touch anything else.
    func cleanCache() {
        lastClean = Date()
        let note = root.appendingPathComponent(".cache-clean")
        if let s = try? String(contentsOf: note, encoding: .utf8), s.hasPrefix("denied"),
           let when = (try? FileManager.default.attributesOfItem(atPath: note.path))?[.modificationDate] as? Date,
           Date().timeIntervalSince(when) < 7 * 86400 {
            return
        }
        let ours = ["The Listening Point.heic", "The Listening Point.jpg"].map { root.appendingPathComponent($0).path }
        var status = "ok"
        do {
            let names = try FileManager.default.contentsOfDirectory(atPath: wallpaperCache.path)
            for p in ours {
                let h = SHA256.hash(data: Data(p.utf8)).map { String(format: "%02x", $0) }.joined()
                var keep: String?
                var st = stat()
                if stat(p, &st) == 0 {
                    let t = Double(st.st_mtimespec.tv_sec) + Double(st.st_mtimespec.tv_nsec) * 1e-9 - 978307200.0
                    keep = withUnsafeBytes(of: t.bitPattern.bigEndian) { $0.map { String(format: "%02x", $0) }.joined() }
                }
                for n in names where n.hasPrefix(h + "-") && !(keep.map { n.hasSuffix("-\($0).bmp") } ?? false) {
                    try FileManager.default.removeItem(at: wallpaperCache.appendingPathComponent(n))
                }
            }
        } catch {
            status = "denied"
        }
        try? "\(status) \(ISO8601DateFormatter().string(from: Date()))\n".write(to: note, atomically: true, encoding: .utf8)
    }

    /// Ask launchd to run the render job now rather than at its next interval (at most every 10 minutes).
    func kick() {
        guard Date().timeIntervalSince(lastKick) > 600 else { return }
        lastKick = Date()
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        p.arguments = ["kickstart", "gui/\(getuid())/com.edd426.listening-point.render"]
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try? p.run()
    }

    func frameURL(for date: Date) -> URL? {
        let c = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: date)
        let day = String(format: "%04d-%02d-%02d", c.year!, c.month!, c.day!)
        let name = String(format: "%02d%02d.jpg", c.hour!, c.minute!)
        let fm = FileManager.default
        let days = root.appendingPathComponent("days")
        let today = days.appendingPathComponent(day).appendingPathComponent(name)
        if fm.fileExists(atPath: today.path) { return today }
        kick()
        let all = (try? fm.contentsOfDirectory(atPath: days.path)) ?? []
        for d in all.sorted(by: >) where d < day {
            let u = days.appendingPathComponent(d).appendingPathComponent(name)
            if fm.fileExists(atPath: u.path) { return u }
        }
        return nil
    }

    func rebuild() {
        windows.forEach { $0.orderOut(nil) }
        windows = NSScreen.screens.map { screen in
            let w = NSWindow(contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false)
            w.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.desktopWindow)) + 1)
            w.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
            w.ignoresMouseEvents = true
            w.isOpaque = true
            w.hasShadow = false
            w.backgroundColor = .black
            w.isReleasedWhenClosed = false
            w.title = "Listening Point"
            let v = NSView(frame: NSRect(origin: .zero, size: screen.frame.size))
            v.wantsLayer = true
            v.layer?.contentsGravity = .resizeAspectFill
            v.layer?.backgroundColor = NSColor.black.cgColor
            w.contentView = v
            w.setFrame(screen.frame, display: false)
            return w
        }
        shown = ""
        tick()
    }

    func tick() {
        if Date().timeIntervalSince(lastClean) > 3600 { cleanCache() }
        if let url = frameURL(for: Date()) {
            if url.path != shown, let src = CGImageSourceCreateWithURL(url as CFURL, nil),
               let img = CGImageSourceCreateImageAtIndex(src, 0, [kCGImageSourceShouldCacheImmediately: true] as CFDictionary) {
                for w in windows {
                    guard let layer = w.contentView?.layer else { continue }
                    if !shown.isEmpty {
                        let fade = CATransition()
                        fade.type = .fade
                        fade.duration = 1.2
                        layer.add(fade, forKey: "contents")
                    }
                    layer.contents = img
                    if !w.isVisible { w.orderFrontRegardless() }
                }
                shown = url.path
            }
        } else if !shown.isEmpty || windows.contains(where: { $0.isVisible }) {
            windows.forEach { $0.orderOut(nil) }
            shown = ""
        }
        schedule()
    }

    func schedule() {
        let now = Date().timeIntervalSince1970
        let next = (floor(now / 60) + 1) * 60 + 0.05
        let t = DispatchSource.makeTimerSource(queue: .main)
        t.schedule(wallDeadline: .now() + (next - now), leeway: .milliseconds(50))
        t.setEventHandler { [weak self] in self?.tick() }
        timer?.cancel()
        timer = t
        t.resume()
    }
}

let path = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "~/Pictures/Wallpapers/The Listening Point"
let live = Live(root: URL(fileURLWithPath: NSString(string: path).expandingTildeInPath))
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let nc = NotificationCenter.default
let wc = NSWorkspace.shared.notificationCenter
nc.addObserver(forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main) { _ in live.rebuild() }
nc.addObserver(forName: .NSSystemClockDidChange, object: nil, queue: .main) { _ in live.tick() }
nc.addObserver(forName: .NSSystemTimeZoneDidChange, object: nil, queue: .main) { _ in live.tick() }
wc.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { _ in live.tick() }
wc.addObserver(forName: NSWorkspace.screensDidWakeNotification, object: nil, queue: .main) { _ in live.tick() }
live.rebuild()
app.run()

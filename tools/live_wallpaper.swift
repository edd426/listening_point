// Shows the Listening Point frame for the current minute on every screen, just above the desktop
// picture and below the desktop icons, switching on each minute with a short cross-fade.
//
// macOS's own time-of-day wallpapers can switch every minute, but the wallpaper agent caches every
// frame it shows as a ~20 MB bitmap and never prunes them, so 1,440 frames a day would fill the
// disk. This window does the per-minute part instead; the system wallpaper is an hourly HEIC of the
// same day, which shows on the lock screen, in Mission Control, while switching Spaces, and
// whenever this isn't running. Each hour this also deletes the agent's bitmaps of older versions of
// our wallpaper files (it needs Full Disk Access for that; the result is in ROOT/.cache-clean).
// Without access macOS shows a "data access blocked" notice, so after a refusal it stops trying;
// after granting access, delete ROOT/.cache-clean and restart it (launchctl kickstart -k ...live).
//
// usage: live_wallpaper [ROOT]   frames are ROOT/days/YYYY-MM-DD/HHMM.jpg (local clock time);
//        when today's frame is missing it uses the same minute from the newest earlier day,
//        and with nothing at all it hides and lets the system wallpaper show. It also starts the
//        render job (a LaunchAgent) at once when today's frames are missing, e.g. after a long sleep,
//        and on waking when the shore was last synced more than an hour ago (the job syncs it first).
//
// It also puts the owner's controls in the menu bar: Light the lamp, and Leave a note… (a small
// panel). The work is done by tools/listener.py (installed beside this binary in src/tools/), run off
// the main thread with a 15 s timeout; see docs/LISTENER.md. The desktop windows stay click-through.
import AppKit
import CryptoKit
import ImageIO
import QuartzCore

let wallpaperCache = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(
    "Library/Containers/com.apple.wallpaper.agent/Data/Library/Caches/com.apple.wallpaper.caches/extension-com.apple.wallpaper.extension.image")
/// tools/shore_sync.py's record, written on every try once the shore is set up (no file: not set up).
let shoreSyncState = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(
    "Library/Application Support/The Listening Point/shore/sync.json")

/// Whether the shore was last synced (tried, online or not) more than an hour ago.
func shoreSyncStale(_ now: Date = Date()) -> Bool {
    guard let data = try? Data(contentsOf: shoreSyncState),
          let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
    let last = (obj["last_attempt_unix"] as? NSNumber)?.doubleValue ?? 0
    return now.timeIntervalSince1970 - last > 3600
}

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
        if let s = try? String(contentsOf: note, encoding: .utf8), s.hasPrefix("denied") {
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

// MARK: - The owner's controls

/// What `listener.py --json` prints under "status". Every field is optional, so a script that adds or
/// drops one still decodes.
struct ListenerStatus: Decodable {
    struct Recipient: Decodable {
        let key: String
        let label: String
    }
    var today: String?
    var lampLitToday: Bool?
    var queued: Int?
    var rejected: Int?
    var lastSend: String?
    var token: String?
    var tokenExpires: String?
    var tokenDaysLeft: Int?
    var error: String?
    var notesToday: Int?
    var notesPerDay: Int?
    var noteMax: Int?
    var recipients: [Recipient]?
    var configError: String?
}

/// One answer from `listener.py --json COMMAND`: result is sent, already, queued, error, refused,
/// failed, drained, empty, busy, ok or status.
struct ListenerReply: Decodable {
    var ok: Bool?
    var result: String?
    var message: String?
    var status: ListenerStatus?
}

final class DataBox {
    var data = Data()
}

/// Runs tools/listener.py. `run` blocks for up to `timeout` seconds, so call it off the main thread.
/// The access key never passes through here: listener.py reads it from the Keychain itself.
final class Listener {
    let script: String?
    let python: String

    init() {
        let exe = (Bundle.main.executableURL ?? URL(fileURLWithPath: CommandLine.arguments[0]))
            .resolvingSymlinksInPath().deletingLastPathComponent()
        // installed: APP/live_wallpaper beside APP/src/tools/listener.py; or built into a folder of the repo
        let candidates = ["src/tools/listener.py", "listener.py", "../tools/listener.py"]
            .map { exe.appendingPathComponent($0).standardizedFileURL.path }
        script = candidates.first { FileManager.default.fileExists(atPath: $0) }
        let venv = exe.appendingPathComponent("venv/bin/python").path
        python = FileManager.default.isExecutableFile(atPath: venv) ? venv : "/usr/bin/python3"
    }

    func run(_ args: [String], input: String? = nil, timeout: TimeInterval = 15) -> (ListenerReply?, String?) {
        guard let script = script else { return (nil, "listener.py is missing: re-run tools/install.sh") }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = ["-I", script, "--json"] + args
        let stdin = Pipe(), stdout = Pipe()
        p.standardInput = stdin
        p.standardOutput = stdout
        p.standardError = FileHandle.standardError
        let exited = DispatchSemaphore(value: 0)
        p.terminationHandler = { _ in exited.signal() }
        do { try p.run() } catch { return (nil, "could not start listener.py") }
        let box = DataBox()
        let read = DispatchSemaphore(value: 0)
        DispatchQueue.global(qos: .utility).async {
            box.data = stdout.fileHandleForReading.readDataToEndOfFile()
            read.signal()
        }
        if let input = input { try? stdin.fileHandleForWriting.write(contentsOf: Data(input.utf8)) }
        try? stdin.fileHandleForWriting.close()
        if exited.wait(timeout: .now() + timeout) == .timedOut {
            p.terminate()
            if exited.wait(timeout: .now() + 2) == .timedOut { kill(p.processIdentifier, SIGKILL) }
            return (nil, "listener.py took longer than \(Int(timeout)) s")
        }
        _ = read.wait(timeout: .now() + 2)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let reply = try? decoder.decode(ListenerReply.self, from: box.data) else {
            return (nil, "listener.py gave no answer (exit \(p.terminationStatus))")
        }
        return (reply, nil)
    }
}

func sentence(_ s: String) -> String {
    s.prefix(1).uppercased() + s.dropFirst()
}

/// The carrier's last evening run is at 23:17 UTC; a note left after it waits for the next evening's,
/// so it arrives a morning later. (late now?, that time on the local clock)
func lastPost(_ now: Date = Date()) -> (late: Bool, local: String) {
    var utc = Calendar(identifier: .gregorian)
    utc.timeZone = TimeZone(identifier: "UTC")!
    let cutoff = utc.date(bySettingHour: 23, minute: 17, second: 0, of: now)!
    let f = DateFormatter()
    f.dateStyle = .none
    f.timeStyle = .short
    return (now >= cutoff, f.string(from: cutoff))
}

/// The "Leave a note…" panel: a recipient picker filled from listener.json, a text box with a
/// character counter, Send and Cancel.
final class NotePanel: NSObject, NSTextViewDelegate, NSWindowDelegate {
    let panel: NSPanel
    let picker = NSPopUpButton(frame: .zero, pullsDown: false)
    let scroll = NSTextView.scrollableTextView()
    let text: NSTextView
    let counter = NSTextField(labelWithString: "")
    let info = NSTextField(wrappingLabelWithString: "")
    let result = NSTextField(wrappingLabelWithString: "")
    let sendButton = NSButton(title: "Send", target: nil, action: nil)
    let cancelButton = NSButton(title: "Cancel", target: nil, action: nil)
    let choices: [[String]]
    let maxChars: Int
    var sending = false
    var done = false
    var onSend: (([String], String) -> Void)?
    var onClose: (() -> Void)?

    init(recipients: [ListenerStatus.Recipient], maxChars: Int) {
        self.maxChars = maxChars
        var choices = recipients.map { [$0.key] }
        var titles = recipients.map { $0.label }
        if recipients.count > 1 {
            choices.append(recipients.map { $0.key })
            titles.append(recipients.count == 2 ? "Both" : "All")
        }
        self.choices = choices
        let w: CGFloat = 460, h: CGFloat = 340, pad: CGFloat = 20
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: w, height: h), styleMask: [.titled, .closable],
                        backing: .buffered, defer: false)
        text = scroll.documentView as! NSTextView
        super.init()
        panel.title = "Leave a note"
        panel.isReleasedWhenClosed = false
        panel.hidesOnDeactivate = false
        panel.delegate = self
        let v = panel.contentView!

        let to = NSTextField(labelWithString: "To:")
        to.frame = NSRect(x: pad, y: h - 42, width: 28, height: 18)
        picker.addItems(withTitles: titles)
        picker.frame = NSRect(x: pad + 32, y: h - 47, width: 200, height: 26)
        scroll.frame = NSRect(x: pad, y: 130, width: w - 2 * pad, height: h - 60 - 130)
        scroll.borderType = .bezelBorder
        scroll.hasVerticalScroller = true
        text.isRichText = false
        text.importsGraphics = false
        text.allowsUndo = true
        text.font = .systemFont(ofSize: 13)
        text.isAutomaticQuoteSubstitutionEnabled = false
        text.isAutomaticDashSubstitutionEnabled = false
        text.isAutomaticTextReplacementEnabled = false
        text.delegate = self
        counter.frame = NSRect(x: w - pad - 140, y: 108, width: 140, height: 16)
        counter.alignment = .right
        counter.font = .monospacedDigitSystemFont(ofSize: 11, weight: .regular)
        let post = lastPost()
        info.stringValue = post.late
            ? "Read as news, not as a request. Tonight's last post left at \(post.local), so this note arrives a morning later."
            : "Read as news, not as a request. Notes go with the evening post and arrive the next morning; one left after \(post.local) arrives a morning later."
        info.frame = NSRect(x: pad, y: 62, width: w - 2 * pad, height: 40)
        info.font = .systemFont(ofSize: 11)
        info.textColor = post.late ? .systemOrange : .secondaryLabelColor
        result.frame = NSRect(x: pad, y: 12, width: w - 2 * pad - 196, height: 42)
        result.font = .systemFont(ofSize: 11)
        cancelButton.frame = NSRect(x: w - pad - 188, y: 16, width: 92, height: 32)
        cancelButton.bezelStyle = .rounded
        cancelButton.keyEquivalent = "\u{1b}"
        cancelButton.target = self
        cancelButton.action = #selector(cancel)
        sendButton.frame = NSRect(x: w - pad - 92, y: 16, width: 92, height: 32)
        sendButton.bezelStyle = .rounded
        sendButton.keyEquivalent = "\r"
        sendButton.keyEquivalentModifierMask = [.command]
        sendButton.toolTip = "Send (⌘↩)"
        sendButton.target = self
        sendButton.action = #selector(send)
        for sub in [to, picker, scroll, counter, info, result, cancelButton, sendButton] as [NSView] {
            v.addSubview(sub)
        }
        updateCounter()
        panel.center()
    }

    func show() {
        if #available(macOS 14.0, *) {
            NSApp.activate()
        } else {
            NSApp.activate(ignoringOtherApps: true)
        }
        panel.makeKeyAndOrderFront(nil)
        panel.orderFrontRegardless()
        panel.makeFirstResponder(text)
    }

    /// Unicode code points after NFC, as listener.py counts them.
    func count() -> Int {
        text.string.precomposedStringWithCanonicalMapping.unicodeScalars.count
    }

    func updateCounter() {
        let n = count()
        counter.stringValue = "\(n) / \(maxChars)"
        counter.textColor = n > maxChars ? .systemRed : .secondaryLabelColor
        let blank = text.string.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        sendButton.isEnabled = !sending && !done && !blank && n <= maxChars
    }

    func textDidChange(_ notification: Notification) {
        updateCounter()
    }

    @objc func send() {
        guard !sending, !done, sendButton.isEnabled else { return }
        sending = true
        text.isEditable = false
        picker.isEnabled = false
        result.textColor = .labelColor
        result.stringValue = "Sending…"
        updateCounter()
        onSend?(choices[max(0, picker.indexOfSelectedItem)], text.string)
    }

    func finished(_ reply: ListenerReply?, _ failure: String?) {
        sending = false
        result.textColor = .labelColor
        switch reply?.result {
        case "sent", "already":
            done = true
            result.stringValue = "Sent."
        case "queued":
            done = true
            result.stringValue = "Saved. It goes when the Mac is next online."
        case "error":
            done = true
            result.stringValue = (reply?.message.map(sentence) ?? "Saved, but not sent.") + ". It stays queued."
            result.textColor = .systemRed
        default:        // refused, failed, or no answer: nothing (or perhaps nothing) was stored
            text.isEditable = true
            picker.isEnabled = true
            result.textColor = .systemRed
            if let failure = failure {
                result.stringValue = sentence(failure) + ". It may have been saved: check the menu before sending again."
            } else {
                result.stringValue = sentence(reply?.message ?? "not sent") + "."
            }
        }
        if done {
            cancelButton.title = "Close"
        }
        updateCounter()
    }

    @objc func cancel() {
        panel.close()
    }

    func windowWillClose(_ notification: Notification) {
        onClose?()
    }
}

/// The menu-bar item.
final class Controls: NSObject, NSMenuDelegate {
    let listener = Listener()
    let work = DispatchQueue.global(qos: .userInitiated)
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let menu = NSMenu()
    let lampItem = NSMenuItem(title: "Light the lamp", action: nil, keyEquivalent: "")
    let noteItem = NSMenuItem(title: "Leave a note…", action: nil, keyEquivalent: "")
    let hintItem = NSMenuItem(title: "", action: nil, keyEquivalent: "")
    var lineItems: [NSMenuItem] = []
    var status: ListenerStatus?
    var problem: String?
    var lighting = false
    var refreshing = false
    var note: NotePanel?

    func start() {
        menu.autoenablesItems = false
        menu.delegate = self
        lampItem.target = self
        lampItem.action = #selector(lightLamp)
        noteItem.target = self
        noteItem.action = #selector(openNote)
        hintItem.isEnabled = false
        for i in [lampItem, noteItem, hintItem, NSMenuItem.separator()] { menu.addItem(i) }
        item.menu = menu
        item.button?.toolTip = "The Listening Point"
        update()
        refresh()
        _ = Timer.scheduledTimer(withTimeInterval: 900, repeats: true) { [weak self] _ in self?.refresh() }
    }

    func menuWillOpen(_ menu: NSMenu) {
        refresh()
    }

    func update() {
        let s = status
        let lit = s?.lampLitToday ?? false
        if let b = item.button {
            if let img = NSImage(systemSymbolName: lit ? "lamp.table.fill" : "lamp.table",
                                 accessibilityDescription: "The Listening Point") {
                img.isTemplate = true
                b.image = img
                b.title = ""
            } else {
                b.image = nil
                b.title = lit ? "◉" : "○"
            }
        }
        let available = listener.script != nil
        if lighting {
            lampItem.title = "Lighting the lamp…"
            lampItem.isEnabled = false
        } else if lit {
            lampItem.title = "The lamp is lit tonight ✓"
            lampItem.isEnabled = false
        } else {
            lampItem.title = "Light the lamp"
            lampItem.isEnabled = available
        }
        var hint: String?
        let recipients = s?.recipients ?? []
        if !available {
            hint = "listener.py is missing: re-run tools/install.sh"
        } else if s != nil && recipients.isEmpty {
            hint = "Notes need listener.json (see docs/LISTENER.md)"
        } else if let n = s?.notesToday, let cap = s?.notesPerDay, n >= cap, note == nil {
            hint = "\(cap) notes today, the most for one day"
        }
        noteItem.isEnabled = available && !recipients.isEmpty && hint == nil
        noteItem.toolTip = hint
        hintItem.title = hint ?? ""
        hintItem.isHidden = hint == nil
        for i in lineItems { menu.removeItem(i) }
        lineItems = statusLines().map { t in
            let i = NSMenuItem(title: t, action: nil, keyEquivalent: "")
            i.isEnabled = false
            return i
        }
        for i in lineItems { menu.addItem(i) }
    }

    func statusLines() -> [String] {
        var lines: [String] = []
        if let p = problem { lines.append(sentence(p)) }
        guard let s = status else { return lines.isEmpty ? ["Checking…"] : lines }
        var first = s.lastSend.flatMap(Controls.when).map { "Last sent: \($0)" } ?? "Nothing sent yet"
        if let q = s.queued, q > 0 { first += " · \(q) waiting to send" }
        lines.append(first)
        switch s.token {
        case "missing":
            lines.append("No key in the Keychain (see docs/LISTENER.md)")
        case "expired":
            lines.append("The key has expired: make a new one (see docs/LISTENER.md)")
        case "rejected":
            lines.append("Not sent: " + (s.error ?? "the key was refused"))
        default:
            if let e = s.error { lines.append("Not sent: " + e) }
            if let d = s.tokenDaysLeft, let e = s.tokenExpires {
                lines.append(d <= 30 ? "Key expires in \(d) day\(d == 1 ? "" : "s")" : "Key expires \(Controls.day(e))")
            }
        }
        if let r = s.rejected, r > 0 { lines.append("\(r) set aside: see listener/rejected/") }
        return lines
    }

    static func when(_ iso: String) -> String? {
        guard let d = ISO8601DateFormatter().date(from: iso) else { return nil }
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        f.doesRelativeDateFormatting = true
        return f.string(from: d)
    }

    static func day(_ ymd: String) -> String {
        let p = DateFormatter()
        p.locale = Locale(identifier: "en_US_POSIX")
        p.dateFormat = "yyyy-MM-dd"
        guard let d = p.date(from: ymd) else { return ymd }
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .none
        return f.string(from: d)
    }

    /// Take an answer: its status, and anything that went wrong outside the status (a refusal, a crash).
    func take(_ reply: ListenerReply?, _ failure: String?) {
        if let s = reply?.status { status = s }
        if let failure = failure {
            problem = failure
        } else if let r = reply, r.result == "refused" || r.result == "failed" {
            problem = r.message
        } else {
            problem = nil
        }
        update()
    }

    func refresh() {
        guard !refreshing else { return }
        refreshing = true
        work.async {
            let (reply, failure) = self.listener.run(["status"])
            DispatchQueue.main.async {
                self.refreshing = false
                self.take(reply, failure)
            }
        }
    }

    /// After a wake, give the network a moment, then send anything queued.
    func wake() {
        work.asyncAfter(deadline: .now() + 20) {
            let (reply, failure) = self.listener.run(["drain"], timeout: 60)
            DispatchQueue.main.async { self.take(reply, failure) }
        }
    }

    @objc func lightLamp() {
        guard !lighting else { return }
        lighting = true
        update()
        work.async {
            let (reply, failure) = self.listener.run(["light"])
            DispatchQueue.main.async {
                self.lighting = false
                self.take(reply, failure)
                if failure != nil { self.refresh() }    // learn what actually happened
            }
        }
    }

    @objc func openNote() {
        if let open = note {
            open.show()
            return
        }
        guard let recipients = status?.recipients, !recipients.isEmpty else { return }
        let panel = NotePanel(recipients: recipients, maxChars: status?.noteMax ?? 500)
        panel.onSend = { [weak self, weak panel] keys, text in
            guard let self = self else { return }
            self.work.async {
                let (reply, failure) = self.listener.run(["note"] + keys.flatMap { ["--to", $0] }, input: text)
                DispatchQueue.main.async {
                    if let s = reply?.status { self.status = s }
                    self.update()
                    panel?.finished(reply, failure)
                }
            }
        }
        panel.onClose = { [weak self] in
            self?.note = nil
            self?.update()
            NSApp.deactivate()
        }
        note = panel
        panel.show()
    }
}

signal(SIGPIPE, SIG_IGN)    // a listener.py that exits before reading its stdin must not kill the helper
let path = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "~/Pictures/Wallpapers/The Listening Point"
let live = Live(root: URL(fileURLWithPath: NSString(string: path).expandingTildeInPath))
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let controls = Controls()
let nc = NotificationCenter.default
let wc = NSWorkspace.shared.notificationCenter
nc.addObserver(forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main) { _ in live.rebuild() }
nc.addObserver(forName: .NSSystemClockDidChange, object: nil, queue: .main) { _ in live.tick() }
nc.addObserver(forName: .NSSystemTimeZoneDidChange, object: nil, queue: .main) { _ in live.tick() }
nc.addObserver(forName: .NSCalendarDayChanged, object: nil, queue: .main) { _ in controls.refresh() }
wc.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { _ in
    live.tick()
    controls.wake()
    // after the network has had a moment, as for the drain: the job syncs the shore before it renders
    DispatchQueue.main.asyncAfter(deadline: .now() + 20) {
        if shoreSyncStale() { live.kick() }
    }
}
wc.addObserver(forName: NSWorkspace.screensDidWakeNotification, object: nil, queue: .main) { _ in live.tick() }
live.rebuild()
controls.start()
app.run()

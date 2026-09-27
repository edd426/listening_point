// Lists the windows that draw the desktop picture: "<window id> onscreen|offscreen <owner> <name>".
// Used by capture_wallpaper.sh to screenshot the wallpaper even behind full-screen apps.
import CoreGraphics

let windows = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as? [[String: Any]] ?? []
for w in windows {
    let owner = w[kCGWindowOwnerName as String] as? String ?? ""
    let name = w[kCGWindowName as String] as? String ?? ""
    guard owner == "WindowManager" && name == "Wallpaper" || owner == "Wallpaper" else { continue }
    let onscreen = (w[kCGWindowIsOnscreen as String] as? Bool) ?? false
    print(w[kCGWindowNumber as String] ?? 0, onscreen ? "onscreen" : "offscreen", owner, name)
}

// usage: make_h24 out.heic img00 img01 ... (image i shown from i*24/N hours local time)
import Foundation
import ImageIO
import AVFoundation

struct TimeItem: Codable { let t: Double; let i: Int }
struct Appearance: Codable { let d: Int; let l: Int }
struct Info: Codable { let ti: [TimeItem]; let ap: Appearance }

let args = CommandLine.arguments
let out = URL(fileURLWithPath: args[1])
let files = Array(args[2...])
let n = files.count
let info = Info(ti: (0..<n).map { TimeItem(t: Double($0) / Double(n), i: $0) },
                ap: Appearance(d: 0, l: n / 2))
let enc = PropertyListEncoder(); enc.outputFormat = .binary
let b64 = try! enc.encode(info).base64EncodedString()

let meta = CGImageMetadataCreateMutable()
let ns = "http://ns.apple.com/namespace/1.0/" as CFString
precondition(CGImageMetadataRegisterNamespaceForPrefix(meta, ns, "apple_desktop" as CFString, nil))
let tag = CGImageMetadataTagCreate(ns, "apple_desktop" as CFString, "h24" as CFString, .string, b64 as CFTypeRef)!
precondition(CGImageMetadataSetTagWithPath(meta, nil, "apple_desktop:h24" as CFString, tag))

let data = NSMutableData()
let dest = CGImageDestinationCreateWithData(data, AVFileType.heic as CFString, n, nil)!
let opts = [kCGImageDestinationLossyCompressionQuality: 0.9] as CFDictionary
for (idx, f) in files.enumerated() {
    let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: f) as CFURL, nil)!
    let img = CGImageSourceCreateImageAtIndex(src, 0, nil)!
    if idx == 0 { CGImageDestinationAddImageAndMetadata(dest, img, meta, opts) }
    else { CGImageDestinationAddImage(dest, img, opts) }
}
precondition(CGImageDestinationFinalize(dest))
try! (data as Data).write(to: out)
print("wrote \(out.path) with \(n) frames")

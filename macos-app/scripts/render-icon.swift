import AppKit

// Build helper: renders the app icon to a 1024×1024 PNG at the path given as the
// first argument. Keep the drawing in sync with Sources/ContextLensApp/AppIcon.swift.
let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "icon-1024.png"

let size = NSSize(width: 1024, height: 1024)
let img = NSImage(size: size)
img.lockFocus()
let xform = NSAffineTransform(); xform.scale(by: 2)   // AppIcon draws at 512; render at 1024
xform.concat()

let s: CGFloat = 512
let bounds = NSRect(x: 0, y: 0, width: s, height: s)
let bg = NSBezierPath(roundedRect: bounds, xRadius: 112, yRadius: 112)
NSGradient(starting: NSColor(calibratedRed: 0.20, green: 0.44, blue: 0.88, alpha: 1),
           ending:   NSColor(calibratedRed: 0.38, green: 0.24, blue: 0.62, alpha: 1))?.draw(in: bg, angle: -60)
let center = NSPoint(x: 232, y: 300); let radius: CGFloat = 150
let lensRect = NSRect(x: center.x - radius, y: center.y - radius, width: radius*2, height: radius*2)
NSColor(calibratedWhite: 0.98, alpha: 1).setFill(); NSBezierPath(ovalIn: lensRect).fill()
NSGraphicsContext.saveGraphicsState(); NSBezierPath(ovalIn: lensRect).addClip()
let bands: [NSColor] = [.systemOrange, .systemBlue, .systemPurple]
let bandH = lensRect.height/CGFloat(bands.count)
for (i,c) in bands.enumerated() { c.withAlphaComponent(0.92).setFill()
  NSBezierPath(rect: NSRect(x: lensRect.minX, y: lensRect.minY + CGFloat(i)*bandH, width: lensRect.width, height: bandH)).fill() }
NSGraphicsContext.restoreGraphicsState()
let ring = NSBezierPath(ovalIn: lensRect); ring.lineWidth = 30; NSColor.white.setStroke(); ring.stroke()
let h = NSBezierPath(); h.move(to: NSPoint(x: center.x + radius*0.72, y: center.y - radius*0.72))
h.line(to: NSPoint(x: 412, y: 120)); h.lineWidth = 50; h.lineCapStyle = .round; NSColor.white.setStroke(); h.stroke()
img.unlockFocus()

guard let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
      let png = rep.representation(using: .png, properties: [:]) else {
    fputs("render failed\n", stderr); exit(1)
}
try! png.write(to: URL(fileURLWithPath: out))
print("wrote \(out)")

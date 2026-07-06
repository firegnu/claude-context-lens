import AppKit

/// The app has no .app bundle when run via `swift run`, so it can't carry an
/// .icns. We draw the Dock icon programmatically and set it at launch via
/// `NSApp.applicationIconImage`. Concept: a magnifying "lens" whose glass shows
/// the orange/blue/purple context-window layers the app inspects.
enum AppIcon {
    static func make() -> NSImage {
        let size = NSSize(width: 512, height: 512)
        let img = NSImage(size: size)
        img.lockFocus()
        defer { img.unlockFocus() }

        let bounds = NSRect(origin: .zero, size: size)

        // rounded-rect background with a blue→purple gradient
        let bg = NSBezierPath(roundedRect: bounds, xRadius: 112, yRadius: 112)
        NSGradient(starting: NSColor(calibratedRed: 0.20, green: 0.44, blue: 0.88, alpha: 1),
                   ending:   NSColor(calibratedRed: 0.38, green: 0.24, blue: 0.62, alpha: 1))?
            .draw(in: bg, angle: -60)

        let center = NSPoint(x: 232, y: 300)
        let radius: CGFloat = 150
        let lensRect = NSRect(x: center.x - radius, y: center.y - radius,
                              width: radius * 2, height: radius * 2)

        // glass base
        NSColor(calibratedWhite: 0.98, alpha: 1).setFill()
        NSBezierPath(ovalIn: lensRect).fill()

        // colored layer bands, clipped to the lens
        NSGraphicsContext.saveGraphicsState()
        NSBezierPath(ovalIn: lensRect).addClip()
        let bands: [NSColor] = [.systemOrange, .systemBlue, .systemPurple]
        let bandH = lensRect.height / CGFloat(bands.count)
        for (i, color) in bands.enumerated() {
            color.withAlphaComponent(0.92).setFill()
            NSBezierPath(rect: NSRect(x: lensRect.minX,
                                      y: lensRect.minY + CGFloat(i) * bandH,
                                      width: lensRect.width, height: bandH)).fill()
        }
        NSGraphicsContext.restoreGraphicsState()

        // lens ring
        let ring = NSBezierPath(ovalIn: lensRect)
        ring.lineWidth = 30
        NSColor.white.setStroke()
        ring.stroke()

        // handle to lower-right
        let handle = NSBezierPath()
        handle.move(to: NSPoint(x: center.x + radius * 0.72, y: center.y - radius * 0.72))
        handle.line(to: NSPoint(x: 412, y: 120))
        handle.lineWidth = 50
        handle.lineCapStyle = .round
        NSColor.white.setStroke()
        handle.stroke()

        return img
    }
}

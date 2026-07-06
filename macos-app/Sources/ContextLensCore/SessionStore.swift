import Foundation

public struct SessionEntry: Identifiable {
    public let id: String
    public let session: Session?
    public let error: String?
    public let directory: URL
}

public struct SessionStore {
    public let root: URL

    public init(root: URL = SessionStore.defaultRoot) {
        self.root = root
    }

    public static var defaultRoot: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".claude-context-lens")
            .appendingPathComponent("sessions")
    }

    public func listSessions() -> [SessionEntry] {
        let fm = FileManager.default
        let dirs = (try? fm.contentsOfDirectory(at: root, includingPropertiesForKeys: [.isDirectoryKey]))
            ?? []
        let entries = dirs.compactMap { url -> SessionEntry? in
            guard (try? url.resourceValues(forKeys: [.isDirectoryKey]))?.isDirectory == true
            else { return nil }
            let name = url.lastPathComponent
            let jsonURL = url.appendingPathComponent("session.json")
            do {
                let data = try Data(contentsOf: jsonURL)
                let session = try JSONDecoder.contract.decode(Session.self, from: data)
                return SessionEntry(id: name, session: session, error: nil, directory: url)
            } catch {
                return SessionEntry(id: name, session: nil,
                                    error: String(describing: error), directory: url)
            }
        }
        return entries.sorted { $0.id > $1.id }
    }

    public func loadBreakdown(sessionDir: URL, relativePath: String) throws -> Breakdown {
        let url = sessionDir.appendingPathComponent(relativePath)
        return try JSONDecoder.contract.decode(Breakdown.self, from: Data(contentsOf: url))
    }

    public func rawURL(sessionDir: URL, relativePath: String) -> URL {
        sessionDir.appendingPathComponent(relativePath)
    }
}

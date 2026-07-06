import SwiftUI

@main
struct ContextLensApp: App {
    @StateObject private var model = AppModel()
    var body: some Scene {
        WindowGroup {
            RootView().environmentObject(model)
                .frame(minWidth: 900, minHeight: 560)
        }
    }
}

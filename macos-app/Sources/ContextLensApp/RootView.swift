import SwiftUI
import UniformTypeIdentifiers

struct RootView: View {
    @EnvironmentObject var model: AppModel
    @State private var showImporter = false
    var body: some View {
        NavigationSplitView {
            SessionListView()
        } content: {
            OutlineView()
        } detail: {
            if let req = model.selectedRequest, let bd = model.breakdown(for: req) {
                VStack(spacing: 0) {
                    Picker("", selection: $model.mode) {
                        ForEach(DetailMode.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                    }.pickerStyle(.segmented).labelsHidden().padding(8).frame(maxWidth: 240)
                    Divider()
                    switch model.mode {
                    case .composition: CompositionView(breakdown: bd)
                    case .diff: DiffView().environmentObject(model)
                    }
                }
            } else {
                Text("Select a request").foregroundStyle(.secondary)
            }
        }
        .toolbar {
            Button { model.reload() } label: { Image(systemName: "arrow.clockwise") }
                .help("刷新当前文件夹")
            Button { showImporter = true } label: { Image(systemName: "folder") }
                .help("打开 sessions 文件夹(当前:\(model.root.path))")
        }
        .fileImporter(isPresented: $showImporter,
                      allowedContentTypes: [.folder],
                      allowsMultipleSelection: false) { result in
            if case let .success(urls) = result, let url = urls.first {
                model.openRoot(url)
            }
        }
    }
}

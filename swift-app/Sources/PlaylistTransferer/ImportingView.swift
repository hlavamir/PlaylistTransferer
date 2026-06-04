import SwiftUI

struct ImportingView: View {
    let message: String

    var body: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.3)
            Text(message)
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
                .animation(.default, value: message)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

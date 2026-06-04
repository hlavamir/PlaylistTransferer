import SwiftUI
import AppKit

struct ResultsView: View {
    let result: ImportResult
    let onImportAnother: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Summary
            VStack(alignment: .leading, spacing: 6) {
                Text(result.playlistName)
                    .font(.system(size: 17, weight: .semibold))
                    .lineLimit(1)
                HStack(spacing: 4) {
                    importBadge
                    if result.matched - result.added > 0 {
                        Text("· \(result.matched - result.added) skipped (already there)")
                            .font(.system(size: 12))
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 24)
            .padding(.vertical, 18)

            Divider()

            // Detail list
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    if result.notFound.isEmpty && result.lowConfidence.isEmpty {
                        HStack(spacing: 8) {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                            Text("All tracks matched successfully")
                                .font(.system(size: 13))
                        }
                        .padding(20)
                    }

                    if !result.notFound.isEmpty {
                        SectionHeader(
                            symbol: "xmark.circle.fill", color: .red,
                            title: "\(result.notFound.count) not in local library"
                        )
                        ForEach(result.notFound) { item in
                            TrackRow(primary: item.name,
                                     detail: "score \(Int(item.score))",
                                     detailColor: .secondary)
                        }
                    }

                    if !result.lowConfidence.isEmpty {
                        SectionHeader(
                            symbol: "exclamationmark.triangle.fill", color: .orange,
                            title: "\(result.lowConfidence.count) low-confidence match(es) — verify manually"
                        )
                        ForEach(result.lowConfidence) { item in
                            TrackRow(primary: item.spotify,
                                     detail: "→ \(item.local)  [\(Int(item.score))]",
                                     detailColor: .orange)
                        }
                    }
                }
                .padding(.bottom, 8)
            }

            Divider()

            Button("Import Another Playlist") { onImportAnother() }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .keyboardShortcut(.return)
                .padding(16)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var importBadge: some View {
        let ratio = result.total > 0 ? Double(result.added) / Double(result.total) : 1
        let color: Color = ratio >= 0.8 ? .green : ratio >= 0.5 ? .orange : .red
        return Text("\(result.added) / \(result.total) tracks imported")
            .font(.system(size: 13, weight: .medium))
            .foregroundStyle(color)
    }
}

// MARK: - Sub-views

private struct SectionHeader: View {
    let symbol: String
    let color: Color
    let title: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: symbol).foregroundStyle(color).font(.system(size: 12))
            Text(title).font(.system(size: 12, weight: .semibold))
        }
        .padding(.horizontal, 20)
        .padding(.top, 14)
        .padding(.bottom, 4)
    }
}

private struct TrackRow: View {
    let primary: String
    let detail: String
    let detailColor: Color

    @State private var isHovered = false
    @State private var copied = false

    var body: some View {
        HStack(alignment: .center, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(primary)
                    .font(.system(size: 12, design: .monospaced))
                    .lineLimit(1)
                Text(detail)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(detailColor.opacity(0.75))
                    .lineLimit(1)
            }

            Spacer()

            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(primary, forType: .string)
                copied = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { copied = false }
            } label: {
                Image(systemName: copied ? "checkmark" : "doc.on.doc")
                    .font(.system(size: 11))
                    .foregroundStyle(copied ? .green : .secondary)
                    .frame(width: 20, height: 20)
                    .animation(.default, value: copied)
            }
            .buttonStyle(.plain)
            .opacity(isHovered ? 1 : 0)
        }
        .padding(.leading, 36)
        .padding(.trailing, 12)
        .padding(.vertical, 4)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(Color.primary.opacity(isHovered ? 0.05 : 0))
                .padding(.horizontal, 8)
        )
        .contentShape(Rectangle())
        .animation(.easeInOut(duration: 0.12), value: isHovered)
        .onHover { isHovered = $0 }
    }
}

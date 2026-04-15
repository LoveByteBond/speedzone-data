//
//  YolRadarLoader.swift
//  SpeedZonePro
//
//  Fetches the community-curated speed zone dataset from the project's
//  GitHub Pages CDN. The feed is produced by a Python scraper that runs
//  periodically against YolRadar.com and geocodes corridor names via
//  Nominatim (OSM).
//
//  Same pattern as OverpassZoneLoader: disk cache with TTL, fallback to
//  bundled data when offline. App merges YolRadar zones, OSM Overpass
//  zones, and user-submitted zones into one effective list.
//

import Foundation

@MainActor
final class YolRadarLoader: ObservableObject {

    // ======================================================================
    // IMPORTANT: change this to YOUR GitHub Pages URL after you set up
    // the speedzone-data repo. Format:
    //     https://<your-github-username>.github.io/speedzone-data/zones.json
    // ======================================================================
    private static let feedURL = URL(
        string: "https://CHANGE_ME.github.io/speedzone-data/zones.json"
    )!

    private static let cacheFilename = "yolradar-zones.json"
    private static let cacheTTLSeconds: TimeInterval = 7 * 24 * 3600  // 7 days

    @Published private(set) var zones: [SpeedZone] = []
    @Published private(set) var lastUpdated: Date?
    @Published private(set) var isLoading = false
    @Published private(set) var lastError: String?

    // MARK: - Public

    /// Load zones: first from disk cache (if fresh), then network in background.
    func load() async {
        // Try cache first
        if let (cached, cachedAt) = loadCache(), Date().timeIntervalSince(cachedAt) < Self.cacheTTLSeconds {
            self.zones = cached
            self.lastUpdated = cachedAt
            return
        }
        // Otherwise fetch
        await refresh()
    }

    /// Force refetch from network.
    func refresh() async {
        isLoading = true
        lastError = nil
        defer { isLoading = false }

        do {
            var req = URLRequest(url: Self.feedURL)
            req.timeoutInterval = 30
            req.setValue("application/json", forHTTPHeaderField: "Accept")

            let (data, response) = try await URLSession.shared.data(for: req)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                throw NSError(domain: "YolRadarLoader", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "HTTP error"])
            }

            let decoded = try JSONDecoder().decode(Feed.self, from: data)
            let parsed: [SpeedZone] = decoded.zones.compactMap { z in
                SpeedZone(
                    id: z.id,
                    name: z.name,
                    entry: .init(latitude: z.entryLat, longitude: z.entryLon),
                    exit:  .init(latitude: z.exitLat,  longitude: z.exitLon),
                    lengthMeters: z.lengthMeters,
                    speedLimitKph: z.speedLimitKph
                )
            }

            self.zones = parsed
            self.lastUpdated = Date()
            saveCache(parsed)
        } catch {
            self.lastError = error.localizedDescription
            // Fall back to cache regardless of age
            if let (cached, cachedAt) = loadCache() {
                self.zones = cached
                self.lastUpdated = cachedAt
            }
        }
    }

    // MARK: - Disk cache

    private var cacheURL: URL? {
        guard let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
            return nil
        }
        return dir.appendingPathComponent(Self.cacheFilename)
    }

    private func loadCache() -> ([SpeedZone], Date)? {
        guard let url = cacheURL,
              let data = try? Data(contentsOf: url),
              let wrapper = try? JSONDecoder().decode(CachedWrapper.self, from: data) else {
            return nil
        }
        return (wrapper.zones, wrapper.cachedAt)
    }

    private func saveCache(_ zones: [SpeedZone]) {
        guard let url = cacheURL else { return }
        let wrapper = CachedWrapper(zones: zones, cachedAt: Date())
        if let data = try? JSONEncoder().encode(wrapper) {
            try? data.write(to: url)
        }
    }

    // MARK: - Decoding shapes

    private struct Feed: Decodable {
        let version: String?
        let count: Int?
        let zones: [FeedZone]
    }

    private struct FeedZone: Decodable {
        let id: String
        let name: String
        let entryLat: Double
        let entryLon: Double
        let exitLat: Double
        let exitLon: Double
        let lengthMeters: Double
        let speedLimitKph: Double
    }

    private struct CachedWrapper: Codable {
        let zones: [SpeedZone]
        let cachedAt: Date
    }
}

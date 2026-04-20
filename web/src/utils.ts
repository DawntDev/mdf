/**
 * Format a byte count into a short human string. e.g. 1_543_221 -> "1.47 MB"
 */
export function formatBytes(bytes?: number): string {
    if (bytes == null || Number.isNaN(bytes)) return "—";
    const units = ["B", "KB", "MB", "GB"];
    let value = bytes;
    let unitIndex = 0;

    while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex += 1;
    }

    return `${value.toFixed(value >= 10 ? 0 : 2)} ${units[unitIndex]}`;
}

/**
 * Format a USD cost with fixed 4 decimals for small values, 2 for large.
 */
export function formatCost(usd?: number | null): string {
    if (usd == null) return "—";
    if (usd < 1) return `$${usd.toFixed(4)}`;
    return `$${usd.toFixed(2)}`;
}

/**
 * Short relative time, e.g. "just now", "12s ago"
 */
export function formatAgo(seconds: number): string {
    if (seconds < 5) return "just now";
    if (seconds < 60) return `${Math.floor(seconds)}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    return `${Math.floor(seconds / 3600)}h ago`;
}
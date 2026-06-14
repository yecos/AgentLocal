/**
 * Shared utilities for bridge API proxy routes.
 * Centralizes auth header construction and common patterns.
 */

const BRIDGE_BASE = process.env.BRIDGE_HOST
  ? `http://${process.env.BRIDGE_HOST}:${process.env.BRIDGE_PORT || "8000"}`
  : `http://localhost:${process.env.BRIDGE_PORT || "8000"}`;

/**
 * Build headers for bridge requests, including Authorization if BRIDGE_TOKEN is set.
 * This fixes B6: auth headers were missing from frontend API calls.
 */
export function bridgeHeaders(jsonContentType = false): Record<string, string> {
  const headers: Record<string, string> = {};
  if (jsonContentType) headers["Content-Type"] = "application/json";
  const token = process.env.BRIDGE_TOKEN;
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

/**
 * Sanitize a filename to prevent path traversal attacks.
 * Removes directory paths and special characters.
 */
export function sanitizeFilename(filename: string): string {
  return filename
    .replace(/^.*[\\/]/, "")       // Remove any directory path
    .replace(/[^\w.\-]/g, "_")     // Replace special chars with underscore
    .replace(/_{2,}/g, "_")        // Collapse multiple underscores
    .substring(0, 255);            // Limit length
}

export { BRIDGE_BASE };

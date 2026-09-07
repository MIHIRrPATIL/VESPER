/**
 * VESPER Local Subnet Auto-Discovery Service.
 *
 * Automatically detects the local Wi-Fi subnet and probes candidate IPs on ports 8000 & 8004
 * for the VESPER Gateway health check endpoint (`/health`) and sync profile (`/sync/profile`).
 */

import { Platform } from "react-native";
import * as Network from "expo-network";

export interface DiscoveredGateway {
  ip: string;
  port: number;
  wsUrl: string;
  httpUrl: string;
  uptimeSeconds?: number;
}

export type DiscoveryProgressCallback = (scannedCount: number, totalCount: number, currentIp: string) => void;

export class SubnetDiscoveryService {
  private static readonly PRIMARY_PORTS = [8000, 8004];
  private static readonly HEALTH_ENDPOINT = "/health";
  private static readonly PROFILE_ENDPOINT = "/sync/profile";
  private static readonly FAST_TIMEOUT_MS = 1500;
  private static readonly SWEEP_TIMEOUT_MS = 1000;

  /**
   * Fast-path Quick Scan for Home / Studio LAN environments (< 500ms).
   * Checks last known URL hint, common workstation IPs, and local gateway candidates.
   */
  public static async quickScan(
    hintHostOrUrl?: string,
    onProgress?: DiscoveryProgressCallback,
    signal?: AbortSignal
  ): Promise<DiscoveredGateway | null> {
    console.log("[Discovery] Running Tier 1 Quick Scan (<500ms)...");
    if (onProgress) onProgress(0, 10, "Fast-path check");

    const fastCandidates: string[] = [];

    // 1. Check user input / last known IP hint
    if (hintHostOrUrl) {
      const cleaned = hintHostOrUrl
        .replace(/^https?:\/\//i, "")
        .replace(/^wss?:\/\//i, "")
        .split("/")[0]
        .split(":")[0]
        .trim();
      if (cleaned && cleaned.length > 0 && !fastCandidates.includes(cleaned)) {
        fastCandidates.push(cleaned);
      }
    }

    // 2. Known workstation hosts and emulator aliases
    const commonHosts = ["192.168.0.107", "192.168.0.202", "127.0.0.1", "localhost"];
    if (Platform.OS === "android") {
      commonHosts.push("10.0.2.2");
    }
    for (const h of commonHosts) {
      if (!fastCandidates.includes(h)) fastCandidates.push(h);
    }

    // 3. Current device subnet gateway (.1) and common suffixes
    try {
      const localIp = await Network.getIpAddressAsync();
      if (localIp && localIp.includes(".") && !localIp.startsWith("127.")) {
        const parts = localIp.split(".");
        if (parts.length === 4) {
          const prefix = `${parts[0]}.${parts[1]}.${parts[2]}`;
          for (const suf of [1, 107, 202, 2, 10, 50, 100]) {
            const ip = `${prefix}.${suf}`;
            if (!fastCandidates.includes(ip) && ip !== localIp) {
              fastCandidates.push(ip);
            }
          }
        }
      }
    } catch {
      // expo-network fallback
    }

    // Probe fast candidates concurrently
    const promises = fastCandidates.map(async (host) => {
      for (const port of this.PRIMARY_PORTS) {
        if (signal?.aborted) return null;
        const res = await this.probeHostPort(host, port, 600, signal);
        if (res) return res;
      }
      return null;
    });

    const results = await Promise.all(promises);
    for (const res of results) {
      if (res) {
        console.log(`[Discovery] Quick-scan hit: Found gateway at ${res.ip}:${res.port}`);
        if (onProgress) onProgress(fastCandidates.length, fastCandidates.length, res.ip);
        return res;
      }
    }

    console.log("[Discovery] Quick scan completed with no match.");
    return null;
  }

  /**
   * Corporate & College Network Subnet Sweep.
   * Tailored for enterprise/campus Wi-Fi where router AP isolation blocks UDP/mDNS.
   * Dynamically extracts the active /24 subnet and sweeps with high concurrency (25 workers) in ~4-5s.
   */
  public static async corporateSubnetSweep(
    onProgress?: DiscoveryProgressCallback,
    signal?: AbortSignal
  ): Promise<DiscoveredGateway | null> {
    console.log("[Discovery] Running Tier 2 Corporate / College Subnet Sweep...");

    // 1. Detect device's active LAN / Wi-Fi IP
    let localIp: string | null = null;
    try {
      localIp = await Network.getIpAddressAsync();
      console.log(`[Discovery] Active device IP: ${localIp}`);
    } catch (e) {
      console.warn("[Discovery] Could not read local IP via expo-network:", e);
    }

    // Determine targeted subnets (prioritizing the device's actual corporate subnet)
    const subnetsToSweep: string[] = [];
    if (localIp && localIp.includes(".") && !localIp.startsWith("127.")) {
      const parts = localIp.split(".");
      if (parts.length === 4) {
        subnetsToSweep.push(`${parts[0]}.${parts[1]}.${parts[2]}`);
      }
    }

    // If local IP detection failed or returned loopback, fallback to standard subnets
    if (subnetsToSweep.length === 0) {
      subnetsToSweep.push("192.168.0", "192.168.1", "10.0.0");
    }

    const candidateIps: string[] = [];

    for (const subnet of subnetsToSweep) {
      // Prioritize common host IP suffixes (.107, .202, .1 router gateway, .100-.115, .2-.25)
      const prioritySuffixes = [
        107, 202, 1, 2, 3, 4, 5, 10, 20, 50,
        100, 101, 102, 103, 104, 105, 106, 108, 109, 110,
        200, 201, 203, 204, 205, 206, 207, 208, 209, 210,
      ];
      for (const suf of prioritySuffixes) {
        const ip = `${subnet}.${suf}`;
        if (!candidateIps.includes(ip) && ip !== localIp) {
          candidateIps.push(ip);
        }
      }

      // Add the remaining /24 hosts (1..254)
      for (let i = 1; i <= 254; i++) {
        const ip = `${subnet}.${i}`;
        if (!candidateIps.includes(ip) && ip !== localIp) {
          candidateIps.push(ip);
        }
      }
    }

    console.log(`[Discovery] Sweeping corporate subnet across ${candidateIps.length} candidate addresses...`);

    // Probe in parallel batches of 25 workers (completes 254 hosts in ~5s)
    const BATCH_SIZE = 25;
    let scanned = 0;

    for (let i = 0; i < candidateIps.length; i += BATCH_SIZE) {
      if (signal?.aborted) return null;

      const batch = candidateIps.slice(i, i + BATCH_SIZE);
      if (onProgress) {
        onProgress(scanned, candidateIps.length, batch[0]);
      }

      const promises = batch.map(async (ip) => {
        for (const port of this.PRIMARY_PORTS) {
          if (signal?.aborted) return null;
          const res = await this.probeHostPort(ip, port, 600, signal);
          if (res) return res;
        }
        return null;
      });

      const results = await Promise.all(promises);
      for (const res of results) {
        if (res) {
          console.log(`[Discovery] Corporate sweep hit: Located VESPER Gateway at ${res.ip}:${res.port}`);
          if (onProgress) {
            onProgress(candidateIps.length, candidateIps.length, res.ip);
          }
          return res;
        }
      }

      scanned += batch.length;
    }

    console.log("[Discovery] Corporate subnet sweep complete. No VESPER Gateway located.");
    return null;
  }

  /**
   * Unified Hybrid Auto-Discovery.
   * Mode 'auto': Tries Quick Scan first (<500ms); if not found, seamlessly runs Corporate Subnet Sweep.
   * Mode 'quick': Only fast-path checks.
   * Mode 'corporate': Full parallel /24 enterprise subnet sweep.
   */
  public static async discover(
    onProgress?: DiscoveryProgressCallback,
    signal?: AbortSignal,
    hintHostOrUrl?: string
  ): Promise<DiscoveredGateway | null> {
    return this.discoverHybrid("auto", onProgress, signal, hintHostOrUrl);
  }

  public static async discoverHybrid(
    mode: "auto" | "quick" | "corporate" = "auto",
    onProgress?: DiscoveryProgressCallback,
    signal?: AbortSignal,
    hintHostOrUrl?: string
  ): Promise<DiscoveredGateway | null> {
    if (mode === "quick") {
      return this.quickScan(hintHostOrUrl, onProgress, signal);
    }

    if (mode === "corporate") {
      return this.corporateSubnetSweep(onProgress, signal);
    }

    // Auto Hybrid Mode:
    // 1. Quick Scan
    const quickResult = await this.quickScan(hintHostOrUrl, onProgress, signal);
    if (quickResult) {
      return quickResult;
    }

    if (signal?.aborted) return null;

    // 2. Fallback to Corporate / Campus Subnet Sweep
    console.log("[Discovery] Quick scan found no gateway. Escalating to corporate subnet sweep...");
    return this.corporateSubnetSweep(onProgress, signal);
  }

  /**
   * Probes a single host and port for the VESPER Gateway health check or sync profile endpoint.
   */
  private static async probeHostPort(
    host: string,
    port: number,
    timeoutMs: number,
    externalSignal?: AbortSignal
  ): Promise<DiscoveredGateway | null> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    if (externalSignal) {
      externalSignal.addEventListener("abort", () => controller.abort());
    }

    try {
      // 1. Check /health
      const healthUrl = `http://${host}:${port}${this.HEALTH_ENDPOINT}`;
      const response = await fetch(healthUrl, {
        method: "GET",
        signal: controller.signal,
        headers: { Accept: "application/json" },
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        const data = await response.json();
        if (data.service === "vesper-gateway" || data.status === "ok") {
          return {
            ip: host,
            port,
            wsUrl: `ws://${host}:${port}/ws`,
            httpUrl: `http://${host}:${port}`,
            uptimeSeconds: data.uptime_seconds,
          };
        }
      }
    } catch {
      // Ignore: IP / port not responding
    } finally {
      clearTimeout(timeoutId);
    }

    // 2. Secondary fallback: check /sync/profile if health failed
    try {
      const syncController = new AbortController();
      const syncTimeoutId = setTimeout(() => syncController.abort(), 600);
      const profileUrl = `http://${host}:${port}${this.PROFILE_ENDPOINT}`;
      const res = await fetch(profileUrl, {
        method: "GET",
        signal: syncController.signal,
        headers: { Accept: "application/json" },
      });
      clearTimeout(syncTimeoutId);

      if (res.ok) {
        const data = await res.json();
        if (data.device_id || data.platform || data.service === "vesper-gateway") {
          return {
            ip: host,
            port,
            wsUrl: `ws://${host}:${port}/ws`,
            httpUrl: `http://${host}:${port}`,
          };
        }
      }
    } catch {
      // Ignore
    }

    return null;
  }
}

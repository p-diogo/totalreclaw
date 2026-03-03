/**
 * Extraction Frequency Tracker
 *
 * Infers extraction events from plugin log output. The plugin logs a message
 * when facts are extracted (e.g., "Auto-extracted and stored N memories"),
 * and the absence of such a message for a given turn means extraction was
 * throttled by C3 (EXTRACT_EVERY_TURNS).
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (section 2.5.3)
 */

import type { ExtractionEvent } from '../types.js';

/** Raw log entry as captured by the ConversationDriver's mock logger. */
export interface LogEntry {
  level: string;
  timestamp: number;
  args: unknown[];
}

/**
 * Analyze plugin logs to identify extraction events and map them to turns.
 *
 * The function scans all log entries for extraction-related patterns and
 * uses agent_end hook invocation markers to correlate extractions with
 * specific conversation turns.
 *
 * Log patterns recognized:
 * - "Auto-extracted and stored N memories" => extraction happened, factCount = N
 * - "extracted N facts" / "stored N memories" => alternative patterns
 * - "Extracting facts" / "Running extraction" => extraction started (count may follow)
 *
 * Turn boundary heuristic:
 * - Each agent_end log marker or extraction log increments the turn counter
 *
 * @param logs - Raw log entries captured from the plugin's logger
 * @param totalTurns - Total number of turns in the conversation (for gap-filling)
 * @returns Array of ExtractionEvent entries, one per turn
 */
export function analyzeExtractionEvents(
  logs: LogEntry[],
  totalTurns: number,
): ExtractionEvent[] {
  // Track which turns had extractions
  const extractionsByTurn = new Map<number, { timestamp: number; factCount: number }>();

  let currentTurn = 0;

  for (const log of logs) {
    const msg = stringifyLogArgs(log.args);

    // Check for extraction success patterns
    const storedMatch = msg.match(/(?:Auto-extracted and )?stored (\d+) memor/i);
    const extractedMatch = msg.match(/extracted (\d+) fact/i);

    if (storedMatch) {
      const factCount = parseInt(storedMatch[1], 10);
      extractionsByTurn.set(currentTurn, {
        timestamp: log.timestamp,
        factCount,
      });
    } else if (extractedMatch) {
      const factCount = parseInt(extractedMatch[1], 10);
      // Only set if we haven't already recorded for this turn (prefer "stored" pattern)
      if (!extractionsByTurn.has(currentTurn)) {
        extractionsByTurn.set(currentTurn, {
          timestamp: log.timestamp,
          factCount,
        });
      }
    }

    // Advance turn counter on agent_end markers
    // The plugin logs when agent_end fires, which marks the boundary between turns
    if (
      msg.includes('agent_end') ||
      msg.includes('Agent end') ||
      msg.includes('end of turn')
    ) {
      currentTurn++;
    }
  }

  // Build full event list covering all turns
  const events: ExtractionEvent[] = [];
  for (let turn = 0; turn < totalTurns; turn++) {
    const extraction = extractionsByTurn.get(turn);
    if (extraction) {
      events.push({
        turnIndex: turn,
        timestamp: extraction.timestamp,
        extracted: true,
        factCount: extraction.factCount,
      });
    } else {
      events.push({
        turnIndex: turn,
        timestamp: 0,
        extracted: false,
        factCount: 0,
      });
    }
  }

  return events;
}

/**
 * Compute extraction frequency summary statistics.
 */
export function computeExtractionStats(events: ExtractionEvent[]): {
  totalTurns: number;
  extractionCount: number;
  totalFactsExtracted: number;
  extractionRate: number;
  extractionTurnIndices: number[];
  avgFactsPerExtraction: number;
} {
  const extractions = events.filter((e) => e.extracted);
  const totalFacts = extractions.reduce((sum, e) => sum + e.factCount, 0);

  return {
    totalTurns: events.length,
    extractionCount: extractions.length,
    totalFactsExtracted: totalFacts,
    extractionRate:
      events.length > 0 ? extractions.length / events.length : 0,
    extractionTurnIndices: extractions.map((e) => e.turnIndex),
    avgFactsPerExtraction:
      extractions.length > 0 ? totalFacts / extractions.length : 0,
  };
}

/**
 * Convert log args array to a single string for pattern matching.
 */
function stringifyLogArgs(args: unknown[]): string {
  return args
    .map((arg) => {
      if (typeof arg === 'string') return arg;
      if (typeof arg === 'number' || typeof arg === 'boolean') return String(arg);
      try {
        return JSON.stringify(arg);
      } catch {
        return String(arg);
      }
    })
    .join(' ');
}

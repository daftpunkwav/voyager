/**
 * @file agentThinking
 * @description Pure helpers for classifying and partitioning agent thinking text,
 * shared by stores and UI to avoid store-to-component reverse dependencies.
 *
 * Responsibilities:
 * - Classify status/scaffold lines (round markers, mode banners, intent
 *   routing) that must not surface as real thinking
 * - Partition thinking text into status lines vs. substantive reasoning
 * - Support persistence (drop scaffolding) and merge dispatch-notice bodies
 *   with substantive thinking
 *
 * This module must not depend on UI-layer components.
 */

/**
 * Status/scaffold lines that must not be presented as real thinking.
 *
 * NOTE: these patterns are legacy RepoPilot status-line formats that arrived
 * with the migrated frontend. The current agent backend never emits them
 * (verified 2026-09-13, no emitter in agent/ or packages/); they remain as
 * display heuristics against model-authored lines that happen to look like
 * scaffolding. There is no live front<->backend text contract here.
 */
export function isStatusLine(ln: string): boolean {
  const t = ln.trim();
  if (!t) return true;
  if (/^\[(状态|执行|规划|规划完成|收口|纠正|阶段)\]/.test(t)) return true;
  if (/^执行\s*·/.test(t)) return true;
  if (/^意图识别:/.test(t)) return true;
  if (/^意图路由\b/.test(t)) return true;
  if (/^正在生成/.test(t)) return true;
  if (/^（思路阶段无内容/.test(t)) return true;
  if (/^\[中间推理\]\s*$/.test(t)) return true;
  // Legacy format: "Hub inferring (round 1/4 · plan_execute)"
  if (/推理中/.test(t) && /第\s*\d+\s*\/\s*\d+\s*轮/.test(t)) return true;
  if (/推理中/.test(t) && /plan_execute|react|tot|reflexion|direct/i.test(t) && t.length < 120) {
    return true;
  }
  if (/^第\s*\d+\s*\/\s*\d+\s*轮\b/.test(t)) return true;
  if (
    /第\s*\d+\s*\/\s*\d+\s*轮\s*·\s*(tot|react|cot|plan_execute|reflexion|direct)\b/i.test(t) &&
    t.length < 80
  ) {
    return true;
  }
  return false;
}

/**
 * Split thinking text into status scaffolding vs. substantive reasoning.
 */
export function partitionThinking(text: string): {
  statusLines: string[];
  realThinking: string;
} {
  const statusLines: string[] = [];
  const realParts: string[] = [];
  for (const raw of text.split('\n')) {
    const ln = raw.trimEnd();
    if (!ln.trim()) {
      if (realParts.length > 0) realParts.push('');
      continue;
    }
    if (isStatusLine(ln)) {
      statusLines.push(ln.trim());
    } else if (/^\[中间推理\]/.test(ln.trim())) {
      const rest = ln.replace(/^\[中间推理\]\s*/, '').trim();
      if (rest) realParts.push(rest);
      else statusLines.push('[中间推理]');
    } else {
      realParts.push(ln);
    }
  }
  return { statusLines, realThinking: realParts.join('\n').trim() };
}

/** Only execution/status markers, no substantive reasoning. */
export function isStatusOnlyThinking(text: string): boolean {
  return !partitionThinking(text).realThinking;
}

/** For persistence: keep only real thinking and drop the scaffolding. */
export function persistableThinking(text: string | undefined | null): string {
  const real = partitionThinking((text ?? '').trim()).realThinking;
  return real;
}

/** True when the body is only a dispatch notice with no substantive content. */
export function isDispatchNoticeOnly(content: string): boolean {
  const t = (content ?? '').trim();
  if (!t || t.length > 280) return false;
  if (/^#{1,3}\s/m.test(t)) return false;
  return (
    /^先交由\s*\*{0,2}[A-Za-z\u4e00-\u9fff]+/.test(t) ||
    /^交由\s*\*{0,2}[A-Za-z\u4e00-\u9fff]+/.test(t)
  );
}

export function coalesceEmptyBodyWithThinking(
  content: string,
  thinking: string | undefined | null
): { content: string; thinking: string } {
  const body = (content ?? '').trim();
  const { realThinking } = partitionThinking((thinking ?? '').trim());
  if (!isDispatchNoticeOnly(body) || realThinking.length < 80) {
    return { content: content ?? '', thinking: thinking ?? '' };
  }
  return {
    content: `${body}\n\n${realThinking}`.trim(),
    thinking: '',
  };
}
